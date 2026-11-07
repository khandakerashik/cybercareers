"""Encrypted, login-protected publishing for GitHub Pages.

GitHub Pages cannot run server-side authentication, so a login form alone would
not protect anything: every JSON file would still be downloadable. Instead the
dashboard data is published only as AES-256-GCM ciphertext, and each person you
allow gets their own username + password that unlocks it in the browser.

Key hierarchy
-------------
* **Master key** (32 random bytes) – yours only. Stored locally in
  ``.vault/master.key`` and as the GitHub Actions secret ``CC_MASTER_KEY``.
* **Data key (DEK)** – fresh random AES-256 key generated on *every* publish.
  All data files are gzip-compressed and encrypted with it.
* **Per-user key (KEK)** – PBKDF2-SHA256(password, per-user salt, 600 000
  iterations). The DEK is wrapped once per user with their KEK, so the browser
  can unwrap it only with a correct username + password.
* To re-wrap a *new* DEK every hour without knowing anyone's password, each
  user's KEK is escrowed encrypted under the master key in
  ``config/users.json``. Removing a user from that file locks them out at the
  next publish, even if they kept an old session.

Nothing secret is ever committed: ``config/users.json`` and ``encrypted/``
contain only salts and ciphertext.
"""
from __future__ import annotations

import base64
import gzip
import hashlib
import hmac
import json
import os
import secrets
import shutil
import unicodedata
from datetime import datetime, timezone
from pathlib import Path

from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.hashes import SHA256
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / 'data'
OUT = ROOT / 'encrypted'
USERS = ROOT / 'config' / 'users.json'
MASTER_FILE = ROOT / '.vault' / 'master.key'
MAGIC = b'CCV1'
ITERATIONS = 600_000
MIN_PASSWORD = 12

# Files the dashboard loads (sealed for the browser) …
FRONTEND_FILES = ('jobs.json', 'sources.json', 'status.json', 'source_health.json', 'progress.json', 'search_queries.json')
# … and collector state that must survive between CI runs (sealed, restored by `unseal`).
STATE_FILES = ('jobs.json', 'status.json', 'source_health.json', 'progress.json', 'feed_state.json', 'ats_discovered.json')
SITE_FILES = ('index.html', 'styles.css', 'app.js', 'auth.js', '.nojekyll')


class VaultError(RuntimeError):
    pass


def b64e(data: bytes) -> str:
    return base64.b64encode(data).decode('ascii')


def b64d(text: str) -> bytes:
    return base64.b64decode(text.encode('ascii'))


def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec='seconds')


def user_id(username: str) -> str:
    """Stable public identifier; the browser computes the same value."""
    norm = unicodedata.normalize('NFC', username.strip().lower())
    return hashlib.sha256(('cybercareers:v1:' + norm).encode('utf-8')).hexdigest()


def derive_kek(password: str, salt: bytes, iterations: int = ITERATIONS) -> bytes:
    pw = unicodedata.normalize('NFC', password).encode('utf-8')
    return PBKDF2HMAC(algorithm=SHA256(), length=32, salt=salt, iterations=iterations).derive(pw)


def seal_bytes(key: bytes, plaintext: bytes, aad: str) -> dict:
    iv = secrets.token_bytes(12)
    return {'iv': b64e(iv), 'ct': b64e(AESGCM(key).encrypt(iv, plaintext, aad.encode()))}


def open_bytes(key: bytes, box: dict, aad: str) -> bytes:
    return AESGCM(key).decrypt(b64d(box['iv']), b64d(box['ct']), aad.encode())


# --------------------------------------------------------------------------- master key

def load_master(required: bool = True) -> bytes | None:
    raw = os.environ.get('CC_MASTER_KEY', '').strip()
    if not raw and MASTER_FILE.is_file():
        raw = MASTER_FILE.read_text(encoding='utf-8').strip()
    if not raw:
        if required:
            raise VaultError('No master key. Run `python -m vault init` or set the CC_MASTER_KEY secret.')
        return None
    try:
        key = base64.urlsafe_b64decode(raw + '=' * (-len(raw) % 4))
    except ValueError as exc:
        raise VaultError('CC_MASTER_KEY is not valid base64') from exc
    if len(key) != 32:
        raise VaultError('CC_MASTER_KEY must decode to 32 bytes')
    return key


def init_master() -> tuple[str, bool]:
    if MASTER_FILE.is_file():
        return MASTER_FILE.read_text(encoding='utf-8').strip(), False
    value = base64.urlsafe_b64encode(secrets.token_bytes(32)).decode().rstrip('=')
    MASTER_FILE.parent.mkdir(parents=True, exist_ok=True)
    MASTER_FILE.write_text(value + '\n', encoding='utf-8')
    try:
        os.chmod(MASTER_FILE, 0o600)
    except OSError:
        pass
    return value, True


# --------------------------------------------------------------------------- users

def read_users() -> dict:
    try:
        data = json.loads(USERS.read_text(encoding='utf-8'))
    except (OSError, ValueError):
        data = {}
    data.setdefault('version', 1)
    data.setdefault('users', {})
    return data


def write_users(data: dict) -> None:
    USERS.parent.mkdir(parents=True, exist_ok=True)
    USERS.write_text(json.dumps(data, indent=2) + '\n', encoding='utf-8')


def check_password(password: str) -> None:
    if len(password) < MIN_PASSWORD:
        raise VaultError(f'Password must be at least {MIN_PASSWORD} characters (a passphrase is ideal).')
    if len(set(password)) < 6:
        raise VaultError('Password is too repetitive.')


def add_user(username: str, password: str, master: bytes, *, replace: bool = False) -> str:
    username = username.strip()
    if not 2 <= len(username) <= 64:
        raise VaultError('Username must be 2–64 characters.')
    check_password(password)
    data = read_users()
    uid = user_id(username)
    if uid in data['users'] and not replace:
        raise VaultError(f'User "{username}" already exists (use `user passwd`).')
    salt = secrets.token_bytes(16)
    kek = derive_kek(password, salt, ITERATIONS)
    data['users'][uid] = {
        'salt': b64e(salt), 'iterations': ITERATIONS,
        'name': seal_bytes(master, username.encode('utf-8'), 'cc-name:' + uid),
        'kek_escrow': seal_bytes(master, kek, 'cc-escrow:' + uid),
        'created_at': data['users'].get(uid, {}).get('created_at') or now(), 'updated_at': now(),
    }
    write_users(data)
    return uid


def remove_user(username: str) -> bool:
    data = read_users()
    removed = data['users'].pop(user_id(username), None) is not None
    if removed:
        write_users(data)
    return removed


def list_users(master: bytes) -> list[dict]:
    rows = []
    for uid, entry in read_users()['users'].items():
        try:
            name = open_bytes(master, entry['name'], 'cc-name:' + uid).decode('utf-8')
        except Exception:
            name = '(cannot decrypt — different master key?)'
        rows.append({'username': name, 'id': uid[:12], 'created_at': entry.get('created_at', ''),
                     'updated_at': entry.get('updated_at', '')})
    return rows


# --------------------------------------------------------------------------- seal / unseal

def seal(master: bytes, *, data_dir: Path = DATA, out_dir: Path = OUT) -> dict:
    users = read_users()['users']
    if not users:
        raise VaultError('No users yet. Add one with `python -m vault user add <name>` first.')
    dek = secrets.token_bytes(32)
    out_dir.mkdir(parents=True, exist_ok=True)
    try:
        previous = json.loads((out_dir / 'keyring.json').read_text(encoding='utf-8')).get('fingerprints', {})
    except (OSError, ValueError):
        previous = {}
    for old in out_dir.glob('*.bin'):
        old.unlink()
    files = {}
    fingerprints = {}
    for name in sorted(set(FRONTEND_FILES) | set(STATE_FILES)):
        path = data_dir / name
        if not path.is_file():
            continue
        raw = path.read_bytes()
        json.loads(raw.decode('utf-8'))  # never publish a corrupt file
        iv = secrets.token_bytes(12)
        packed = gzip.compress(raw, compresslevel=9, mtime=0)
        blob = MAGIC + iv + AESGCM(dek).encrypt(iv, packed, ('cc-file:' + name).encode())
        stem = name.rsplit('.', 1)[0]
        (out_dir / f'{stem}.bin').write_bytes(blob)
        files[name] = {'path': f'{stem}.bin', 'bytes': len(blob)}
        # Keyed fingerprint: lets CI detect changes without revealing content.
        fingerprints[name] = hmac.new(master, b'cc-fp:' + name.encode() + b':' + raw, 'sha256').hexdigest()[:32]
    wrapped = {}
    for uid, entry in users.items():
        kek = open_bytes(master, entry['kek_escrow'], 'cc-escrow:' + uid)
        box = seal_bytes(kek, dek, 'cc-dek:' + uid)
        wrapped[uid] = {'salt': entry['salt'], 'iterations': int(entry.get('iterations', ITERATIONS)), **box}
    keyring = {'version': 1, 'sealed_at': now(), 'cipher': 'AES-256-GCM', 'kdf': 'PBKDF2-SHA256',
               'files': files, 'fingerprints': fingerprints, 'users': wrapped, 'ci': seal_bytes(master, dek, 'cc-dek:ci')}
    (out_dir / 'keyring.json').write_text(json.dumps(keyring, indent=1) + '\n', encoding='utf-8')
    keyring['changed'] = sorted(n for n in fingerprints if previous.get(n) != fingerprints[n])
    return keyring


def _read_keyring(out_dir: Path) -> dict:
    try:
        return json.loads((out_dir / 'keyring.json').read_text(encoding='utf-8'))
    except (OSError, ValueError) as exc:
        raise VaultError(f'No readable keyring in {out_dir}') from exc


def decrypt_file(dek: bytes, blob: bytes, name: str) -> bytes:
    if blob[:4] != MAGIC:
        raise VaultError(f'{name}: not a CyberCareers vault file')
    return gzip.decompress(AESGCM(dek).decrypt(blob[4:16], blob[16:], ('cc-file:' + name).encode()))


def unseal(master: bytes, *, data_dir: Path = DATA, out_dir: Path = OUT, names=STATE_FILES,
           overwrite: bool = True) -> list[str]:
    """Restore collector state from the published vault (used at the start of CI)."""
    if not (out_dir / 'keyring.json').is_file():
        return []
    keyring = _read_keyring(out_dir)
    dek = open_bytes(master, keyring['ci'], 'cc-dek:ci')
    restored = []
    data_dir.mkdir(parents=True, exist_ok=True)
    for name in names:
        info = keyring.get('files', {}).get(name)
        if not info:
            continue
        target = data_dir / name
        if target.exists() and not overwrite:
            continue
        target.write_bytes(decrypt_file(dek, (out_dir / info['path']).read_bytes(), name))
        restored.append(name)
    return restored


def verify_login(username: str, password: str, *, out_dir: Path = OUT) -> list[str]:
    """Do exactly what the browser does; returns the decryptable file names."""
    keyring = _read_keyring(out_dir)
    uid = user_id(username)
    entry = keyring['users'].get(uid)
    if not entry:
        raise VaultError('Unknown user in the published keyring (re-run seal after adding users).')
    kek = derive_kek(password, b64d(entry['salt']), int(entry['iterations']))
    try:
        dek = open_bytes(kek, entry, 'cc-dek:' + uid)
    except Exception as exc:
        raise VaultError('Wrong password.') from exc
    ok = []
    for name, info in keyring['files'].items():
        decrypt_file(dek, (out_dir / info['path']).read_bytes(), name)
        ok.append(name)
    return ok


# --------------------------------------------------------------------------- static site

ROBOTS_TXT = 'User-agent: *\nDisallow: /\n'


def build_site(out: Path, *, vault_dir: Path = OUT) -> Path:
    if not (vault_dir / 'keyring.json').is_file():
        raise VaultError('Nothing sealed yet. Run `python -m vault seal` first.')
    if out.exists():
        shutil.rmtree(out)
    out.mkdir(parents=True)
    for name in SITE_FILES:
        src = ROOT / name
        if src.is_file():
            shutil.copy2(src, out / name)
    shutil.copytree(ROOT / 'assets', out / 'assets')
    shutil.copytree(vault_dir, out / 'encrypted')
    (out / 'config.js').write_text("window.CC_CONFIG = Object.freeze({ mode: 'vault', vault: 'encrypted/' });\n",
                                   encoding='utf-8')
    (out / 'robots.txt').write_text(ROBOTS_TXT, encoding='utf-8')
    (out / '.nojekyll').write_text('', encoding='utf-8')
    # Belt and braces: never ship plaintext data or config into the site.
    for leftover in list(out.rglob('*.json')):
        if leftover.name != 'keyring.json':
            raise VaultError(f'Refusing to publish plaintext JSON: {leftover}')
    return out
