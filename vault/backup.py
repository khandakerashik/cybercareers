"""Best-effort repository backup of an already sealed vault.

The publishing checkout is read-only here. Each attempt starts from the latest
remote branch in a disposable worktree, and never merges or force-pushes data.
"""
from __future__ import annotations

import base64
import json
import os
import re
import shutil
import stat
import subprocess
import tempfile
import uuid
from datetime import datetime
from pathlib import Path

from . import FRONTEND_FILES, MAGIC, STATE_FILES

NETWORK_TIMEOUT = 30
LOCAL_TIMEOUT = 15
ALLOWED_FILES = frozenset(FRONTEND_FILES) | frozenset(STATE_FILES)
IDENTITY = ['-c', 'user.name=github-actions[bot]', '-c',
            'user.email=41898282+github-actions[bot]@users.noreply.github.com']


class BackupError(Exception):
    """A deliberately generic error: subprocess output can contain credentials."""


def _git(repo: Path, args: list[str], *, check: bool = True,
         timeout: int = LOCAL_TIMEOUT) -> subprocess.CompletedProcess:
    try:
        result = subprocess.run(
            ['git', '-C', str(repo), *args], capture_output=True,
            env={**os.environ, 'GIT_TERMINAL_PROMPT': '0'}, timeout=timeout,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise BackupError('git_unavailable_or_timed_out') from exc
    if check and result.returncode:
        raise BackupError('git_operation_failed')
    return result


def _result(status: str, reason: str, attempts: int = 0) -> dict:
    return {'status': status, 'reason': reason, 'attempts': attempts}


def _box(value: object, *, user: bool = False) -> bool:
    keys = {'iv', 'ct', 'salt', 'iterations'} if user else {'iv', 'ct'}
    if not isinstance(value, dict) or set(value) != keys:
        return False
    try:
        valid = (len(base64.b64decode(value['iv'], validate=True)) == 12
                 and len(base64.b64decode(value['ct'], validate=True)) == 48)
        if user:
            valid = valid and len(base64.b64decode(value['salt'], validate=True)) == 16
            valid = valid and type(value['iterations']) is int and value['iterations'] > 0
        return bool(valid)
    except (ValueError, TypeError):
        return False


def _read_regular(directory: int, name: str, limit: int) -> bytes:
    fd = os.open(name, os.O_RDONLY | os.O_NOFOLLOW, dir_fd=directory)
    with os.fdopen(fd, 'rb') as stream:
        info = os.fstat(stream.fileno())
        if not stat.S_ISREG(info.st_mode) or info.st_size > limit:
            raise ValueError('invalid file')
        data = stream.read(limit + 1)
        if len(data) > limit:
            raise ValueError('oversized file')
        return data


def _snapshot(repo: Path) -> tuple[dict[str, bytes], str]:
    """Read one sealed generation, excluding everything outside its allowlist."""
    directory = os.open(repo / 'encrypted', os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        raw = _read_regular(directory, 'keyring.json', 4 * 1024 * 1024)
        keyring = json.loads(raw)
        if not isinstance(keyring, dict) or set(keyring) != {
            'version', 'sealed_at', 'cipher', 'kdf', 'files', 'fingerprints', 'users', 'ci'
        }:
            raise ValueError('invalid keyring')
        if (keyring['version'] != 1 or keyring['cipher'] != 'AES-256-GCM'
                or keyring['kdf'] != 'PBKDF2-SHA256' or not _box(keyring['ci'])):
            raise ValueError('invalid keyring')
        datetime.fromisoformat(keyring['sealed_at'].replace('Z', '+00:00'))
        files, fingerprints, users = keyring['files'], keyring['fingerprints'], keyring['users']
        if (not isinstance(files, dict) or 'jobs.json' not in files
                or not set(files) <= ALLOWED_FILES or not isinstance(fingerprints, dict)
                or set(fingerprints) != set(files) or not isinstance(users, dict) or not users):
            raise ValueError('invalid manifest')
        if any(not isinstance(fp, str) or not re.fullmatch(r'[0-9a-f]{32}', fp)
               for fp in fingerprints.values()):
            raise ValueError('invalid fingerprints')
        if any(not re.fullmatch(r'[0-9a-f]{64}', uid) or not _box(box, user=True)
               for uid, box in users.items()):
            raise ValueError('invalid users')
        snapshot = {'keyring.json': raw}
        for name, entry in files.items():
            path = name.rsplit('.', 1)[0] + '.bin'
            if (not isinstance(entry, dict) or set(entry) != {'path', 'bytes'}
                    or entry['path'] != path or type(entry['bytes']) is not int):
                raise ValueError('invalid manifest path')
            blob = _read_regular(directory, path, 64 * 1024 * 1024)
            if len(blob) < 32 or not blob.startswith(MAGIC) or len(blob) != entry['bytes']:
                raise ValueError('invalid ciphertext')
            snapshot[path] = blob
        if _read_regular(directory, 'keyring.json', 4 * 1024 * 1024) != raw:
            raise ValueError('snapshot changed')
        return snapshot, fingerprints['jobs.json']
    finally:
        os.close(directory)


def _protected_state(repo: Path, commit: str) -> bytes:
    # Tree/blob IDs include all contents, names and file modes; absent paths also
    # compare correctly. Always compare against the original workflow commit.
    return _git(repo, ['ls-tree', '-z', '--full-tree', commit, '--',
                       'encrypted', 'config/users.json']).stdout


def _remote_fingerprint(repo: Path, commit: str) -> str | None:
    result = _git(repo, ['show', f'{commit}:encrypted/keyring.json'], check=False)
    try:
        keyring = json.loads(result.stdout) if result.returncode == 0 else {}
        fingerprint = keyring.get('fingerprints', {}).get('jobs.json')
        entry = keyring.get('files', {}).get('jobs.json', {})
        if (keyring.get('version') == 1 and entry.get('path') == 'jobs.bin'
                and isinstance(fingerprint, str) and re.fullmatch(r'[0-9a-f]{32}', fingerprint)):
            return fingerprint
    except (ValueError, TypeError, AttributeError):
        pass
    return None


def backup_encrypted(repo: Path, branch: str, attempts: int = 3) -> dict:
    """Save ciphertext atop a current branch, preserving concurrent vault edits."""
    if os.name != 'posix':
        return _result('skipped', 'unsupported_platform')
    repo = Path(repo).resolve()
    if (not isinstance(branch, str) or not branch or branch.startswith('-')
            or len(branch) > 250 or any(ord(char) < 32 for char in branch)):
        return _result('skipped', 'invalid_branch')
    attempts = min(3, max(1, int(attempts)))
    ref = 'refs/cybercareers-backup/' + uuid.uuid4().hex
    completed = 0
    try:
        if _git(repo, ['check-ref-format', 'refs/heads/' + branch], check=False).returncode:
            return _result('skipped', 'invalid_branch')
        root = Path(_git(repo, ['rev-parse', '--show-toplevel']).stdout.decode().strip()).resolve()
        if root != repo:
            return _result('failed', 'repository_root_required')
        original = _git(repo, ['rev-parse', '--verify', 'HEAD']).stdout.decode().strip()
        protected = _protected_state(repo, original)
        try:
            snapshot, fingerprint = _snapshot(repo)
        except (OSError, ValueError, TypeError, AttributeError):
            return _result('failed', 'invalid_snapshot')
        for completed in range(1, attempts + 1):
            _git(repo, ['fetch', '--no-tags', '--no-write-fetch-head', 'origin',
                        f'refs/heads/{branch}:{ref}'], timeout=NETWORK_TIMEOUT)
            tip = _git(repo, ['rev-parse', '--verify', ref]).stdout.decode().strip()
            if _protected_state(repo, tip) != protected:
                return _result('skipped', 'concurrent_vault_or_access_change', completed)
            if _remote_fingerprint(repo, tip) == fingerprint:
                return _result('unchanged', 'jobs_already_backed_up', completed)
            with tempfile.TemporaryDirectory(prefix='cc-vault-backup-') as temporary:
                worktree = Path(temporary) / 'worktree'
                try:
                    _git(repo, ['worktree', 'add', '--detach', str(worktree), tip])
                    destination = worktree / 'encrypted'
                    if destination.is_symlink():
                        return _result('failed', 'invalid_remote_snapshot', completed)
                    if destination.exists():
                        shutil.rmtree(destination)
                    destination.mkdir()
                    for name, blob in snapshot.items():
                        (destination / name).write_bytes(blob)
                    _git(worktree, ['add', '--all', '--', 'encrypted'])
                    if not _git(worktree, ['diff', '--cached', '--name-only']).stdout:
                        return _result('unchanged', 'snapshot_already_backed_up', completed)
                    _git(worktree, [*IDENTITY, 'commit', '-m', 'chore: update encrypted job vault'])
                    changed = _git(worktree, ['diff-tree', '--no-commit-id', '--name-only',
                                               '-r', '-z', 'HEAD']).stdout.split(b'\0')
                    if any(path and not path.startswith(b'encrypted/') for path in changed):
                        return _result('failed', 'unexpected_backup_changes', completed)
                    pushed = _git(worktree, ['push', 'origin', f'HEAD:refs/heads/{branch}'],
                                  check=False, timeout=NETWORK_TIMEOUT)
                    if pushed.returncode == 0:
                        return _result('saved', 'encrypted_snapshot_saved', completed)
                finally:
                    # Only our disposable worktree is removed; no reset, stash,
                    # checkout, merge or rebase touches the publishing checkout.
                    _git(repo, ['worktree', 'remove', '--force', str(worktree)], check=False)
        return _result('failed', 'push_rejected_or_unavailable', completed)
    except (BackupError, OSError, ValueError):
        return _result('failed', 'backup_unavailable', completed)
    finally:
        try:
            _git(repo, ['update-ref', '-d', ref], check=False)
        except BackupError:
            pass


def main() -> int:
    ref = os.environ.get('GITHUB_REF', '')
    if ref.startswith('refs/heads/'):
        result = backup_encrypted(Path(os.environ.get('GITHUB_WORKSPACE') or Path.cwd()),
                                  ref[len('refs/heads/'):])
    else:
        result = _result('skipped', 'branch_ref_required')
    # Only fixed status/reason values are emitted, never git output or vault data.
    print(f"Encrypted backup: {result['status']} ({result['reason']}).")
    if (result['status'] == 'failed'
            or result['reason'] == 'concurrent_vault_or_access_change'):
        print(f"::warning::Encrypted repository backup was not saved ({result['reason']}).")
    output = os.environ.get('GITHUB_OUTPUT')
    summary = os.environ.get('GITHUB_STEP_SUMMARY')
    if output:
        with open(output, 'a', encoding='utf-8') as stream:
            stream.write(f"backup_status={result['status']}\nbackup_reason={result['reason']}\n")
    if summary:
        with open(summary, 'a', encoding='utf-8') as stream:
            stream.write(f"### Encrypted repository backup\n\nStatus: **{result['status']}**. "
                         f"Reason: `{result['reason']}`. Publishing checkout preserved.\n\n")
    return 1 if result['status'] == 'failed' else 0


if __name__ == '__main__':
    raise SystemExit(main())
