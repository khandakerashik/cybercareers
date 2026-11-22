"""Real local remotes exercise backup races without contacting GitHub."""
from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path
from types import SimpleNamespace

import pytest

import vault
from vault import backup

pytestmark = pytest.mark.skipif(
    os.name != 'posix' or shutil.which('git') is None,
    reason='Encrypted backup integration tests require POSIX and Git (Actions uses Ubuntu).',
)


def git(repo, *args, check=True):
    return subprocess.run(
        ['git', '-C', str(repo), '-c', 'user.name=Backup Test', '-c',
         'user.email=backup@example.test', *args], capture_output=True,
        text=True, check=check, timeout=15,
    ).stdout.strip()


@pytest.fixture
def repository(tmp_path, monkeypatch):
    remote = tmp_path / 'remote.git'
    subprocess.run(['git', 'init', '--bare', '--initial-branch=main', str(remote)],
                   capture_output=True, check=True)
    checkout = tmp_path / 'workflow'
    subprocess.run(['git', 'clone', str(remote), str(checkout)], capture_output=True, check=True)
    monkeypatch.setattr(vault, 'ITERATIONS', 1000)
    monkeypatch.setattr(vault, 'USERS', checkout / 'config' / 'users.json')
    master = b't' * 32
    vault.add_user('tester', 'test-only long passphrase 42!', master)

    def seal(where=checkout, jobs=None):
        data = where / 'data'
        data.mkdir(exist_ok=True)
        if jobs is not None:
            (data / 'jobs.json').write_text(json.dumps(jobs))
        with monkeypatch.context() as context:
            context.setattr(vault, 'USERS', where / 'config' / 'users.json')
            vault.seal(master, data_dir=data, out_dir=where / 'encrypted')

    seal(jobs=[{'id': 'original', 'title': 'Original role'}])
    (checkout / '.gitignore').write_text('data/\n')
    (checkout / 'app.js').write_text('original code\n')
    git(checkout, 'add', '.gitignore', 'app.js', 'config/users.json', 'encrypted')
    git(checkout, 'commit', '-m', 'Initial sealed vault')
    git(checkout, 'push', 'origin', 'main')
    writer = tmp_path / 'writer'
    subprocess.run(['git', 'clone', str(remote), str(writer)], capture_output=True, check=True)
    return SimpleNamespace(checkout=checkout, remote=remote, writer=writer, seal=seal)


def local_state(repo):
    return {
        'head': git(repo, 'rev-parse', 'HEAD'),
        'status': git(repo, 'status', '--porcelain'),
        'index': (repo / '.git' / 'index').read_bytes(),
        'code': (repo / 'app.js').read_bytes(),
        'encrypted': {p.name: p.read_bytes() for p in (repo / 'encrypted').iterdir()},
    }


def assert_preserved(repository, before):
    assert local_state(repository.checkout) == before
    assert not git(repository.checkout, 'for-each-ref', 'refs/cybercareers-backup')
    assert git(repository.checkout, 'worktree', 'list', '--porcelain').count('worktree ') == 1


def advance_code(repository, value='newer code\n'):
    (repository.writer / 'app.js').write_text(value)
    git(repository.writer, 'add', 'app.js')
    git(repository.writer, 'commit', '-m', 'Concurrent application change')
    git(repository.writer, 'push', 'origin', 'main')


def test_backup_preserves_new_remote_code_and_original_checkout(repository):
    repository.seal(jobs=[{'id': 'new', 'title': 'New role'}])
    # Files outside the manifest must never be included, even under encrypted/.
    (repository.checkout / 'encrypted' / 'private-notes.txt').write_text('never publish this')
    before = local_state(repository.checkout)
    advance_code(repository)
    result = backup.backup_encrypted(repository.checkout, 'main')
    assert result == {'status': 'saved', 'reason': 'encrypted_snapshot_saved', 'attempts': 1}
    assert git(repository.remote, 'show', 'main:app.js') == 'newer code'
    assert git(repository.remote, 'show', 'main:encrypted/keyring.json') == before['encrypted']['keyring.json'].decode().strip()
    assert 'private-notes.txt' not in git(repository.remote, 'ls-tree', '-r', '--name-only', 'main')
    assert_preserved(repository, before)


def test_push_race_refetches_and_retries_without_force(repository, monkeypatch):
    repository.seal(jobs=[{'id': 'new'}])
    before = local_state(repository.checkout)
    original_git = backup._git
    pushes = []

    def race(repo, args, **kwargs):
        if args[0] == 'push':
            pushes.append(args)
            if len(pushes) == 1:
                advance_code(repository, 'code committed during backup\n')
        return original_git(repo, args, **kwargs)

    monkeypatch.setattr(backup, '_git', race)
    result = backup.backup_encrypted(repository.checkout, 'main')
    assert result['status'] == 'saved' and result['attempts'] == 2
    assert pushes == [['push', 'origin', 'HEAD:refs/heads/main']] * 2
    assert git(repository.remote, 'show', 'main:app.js') == 'code committed during backup'
    assert_preserved(repository, before)


@pytest.mark.parametrize('changed_path', ['encrypted', 'config/users.json'])
def test_concurrent_vault_or_access_change_is_preserved(repository, changed_path):
    repository.seal(jobs=[{'id': 'local-new'}])
    before = local_state(repository.checkout)
    if changed_path == 'encrypted':
        repository.seal(repository.writer, [{'id': 'remote-newer'}])
    else:
        path = repository.writer / changed_path
        config = json.loads(path.read_text())
        config['users'] = {}  # A concurrent access revocation must survive.
        path.write_text(json.dumps(config))
    git(repository.writer, 'add', changed_path)
    git(repository.writer, 'commit', '-m', 'Concurrent protected state change')
    git(repository.writer, 'push', 'origin', 'main')
    tip = git(repository.remote, 'rev-parse', 'main')
    result = backup.backup_encrypted(repository.checkout, 'main')
    assert result['status'] == 'skipped'
    assert result['reason'] == 'concurrent_vault_or_access_change'
    assert git(repository.remote, 'rev-parse', 'main') == tip
    assert_preserved(repository, before)


def test_rejected_backup_retries_same_jobs_on_next_run(repository, capsys):
    repository.seal(jobs=[{'id': 'new'}])
    before = local_state(repository.checkout)
    hook = repository.remote / 'hooks' / 'pre-receive'
    hook.write_text('#!/bin/sh\necho synthetic-sensitive-marker >&2\nexit 1\n')
    hook.chmod(0o700)
    tip = git(repository.remote, 'rev-parse', 'main')
    result = backup.backup_encrypted(repository.checkout, 'main')
    assert result == {'status': 'failed', 'reason': 'push_rejected_or_unavailable', 'attempts': 3}
    assert git(repository.remote, 'rev-parse', 'main') == tip
    captured = capsys.readouterr()
    assert 'synthetic-sensitive-marker' not in repr(result) + captured.out + captured.err
    assert_preserved(repository, before)
    hook.unlink()
    # No new jobs/seal invocation: comparing with the repository, not restored
    # cache state, makes the previously missed durable backup retry successfully.
    assert backup.backup_encrypted(repository.checkout, 'main')['status'] == 'saved'
    assert_preserved(repository, before)


def test_same_jobs_skip_fresh_ciphertext_only_commit(repository):
    repository.seal()  # Fresh random ciphertext, identical keyed jobs fingerprint.
    before = local_state(repository.checkout)
    tip = git(repository.remote, 'rev-parse', 'main')
    result = backup.backup_encrypted(repository.checkout, 'main')
    assert result['status'] == 'unchanged'
    assert result['reason'] == 'jobs_already_backed_up'
    assert git(repository.remote, 'rev-parse', 'main') == tip
    assert_preserved(repository, before)


@pytest.mark.parametrize('invalid', ['traversal', 'symlink'])
def test_invalid_snapshot_is_not_copied(repository, invalid, tmp_path):
    repository.seal(jobs=[{'id': 'new'}])
    keyring_path = repository.checkout / 'encrypted' / 'keyring.json'
    if invalid == 'traversal':
        keyring = json.loads(keyring_path.read_text())
        keyring['files']['jobs.json']['path'] = '../data/jobs.json'
        keyring_path.write_text(json.dumps(keyring))
    else:
        target = tmp_path / 'ciphertext.bin'
        jobs = repository.checkout / 'encrypted' / 'jobs.bin'
        target.write_bytes(jobs.read_bytes())
        jobs.unlink()
        jobs.symlink_to(target)
    before = local_state(repository.checkout)
    tip = git(repository.remote, 'rev-parse', 'main')
    assert backup.backup_encrypted(repository.checkout, 'main')['reason'] == 'invalid_snapshot'
    assert git(repository.remote, 'rev-parse', 'main') == tip
    assert_preserved(repository, before)


def test_cli_skips_nonbranch_ref_and_emits_safe_status(tmp_path, monkeypatch, capsys):
    output, summary = tmp_path / 'output', tmp_path / 'summary'
    monkeypatch.setenv('GITHUB_REF', 'refs/pull/123/merge')
    monkeypatch.setenv('GITHUB_OUTPUT', str(output))
    monkeypatch.setenv('GITHUB_STEP_SUMMARY', str(summary))
    assert backup.main() == 0
    assert output.read_text() == 'backup_status=skipped\nbackup_reason=branch_ref_required\n'
    assert '**skipped**' in summary.read_text()
    assert 'branch_ref_required' in capsys.readouterr().out


@pytest.mark.parametrize(('status', 'reason', 'exit_code'), [
    ('failed', 'push_rejected_or_unavailable', 1),
    ('skipped', 'concurrent_vault_or_access_change', 0),
])
def test_cli_warns_when_backup_cannot_be_saved(monkeypatch, capsys, status, reason, exit_code):
    monkeypatch.setenv('GITHUB_REF', 'refs/heads/main')
    monkeypatch.delenv('GITHUB_OUTPUT', raising=False)
    monkeypatch.delenv('GITHUB_STEP_SUMMARY', raising=False)
    monkeypatch.setattr(backup, 'backup_encrypted', lambda *args: {
        'status': status, 'reason': reason, 'attempts': 1,
    })
    assert backup.main() == exit_code
    assert f'::warning::Encrypted repository backup was not saved ({reason}).' in capsys.readouterr().out
