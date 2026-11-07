"""Encrypted GitHub Pages vault: login, revocation, CI restore, no plaintext in the site."""
import base64
import json
import secrets

import pytest

import vault as v


@pytest.fixture
def env(tmp_path, monkeypatch):
    key = base64.urlsafe_b64encode(secrets.token_bytes(32)).decode().rstrip('=')
    monkeypatch.setenv('CC_MASTER_KEY', key)
    monkeypatch.setattr(v, 'USERS', tmp_path / 'config' / 'users.json')
    monkeypatch.setattr(v, 'ITERATIONS', 1000)  # fast tests; production uses 600k
    data = tmp_path / 'data'
    data.mkdir()
    (data / 'jobs.json').write_text(json.dumps({'jobs': [{'title': 'SOC Analyst'}]}))
    (data / 'sources.json').write_text('[]')
    return tmp_path, v.load_master(), data, tmp_path / 'encrypted'


def test_login_revocation_and_ci_restore(env):
    root, master, data, out = env
    v.add_user('Ashik', 'correct horse battery staple', master)
    v.add_user('reviewer', 'Another-Strong-Pass-2026', master)
    ring = v.seal(master, data_dir=data, out_dir=out)
    assert 'jobs.json' in ring['changed'] and len(ring['users']) == 2
    assert v.verify_login('ashik', 'correct horse battery staple', out_dir=out)
    with pytest.raises(v.VaultError):
        v.verify_login('ashik', 'wrong password!!', out_dir=out)
    blob = (out / 'jobs.bin').read_bytes()
    assert b'SOC Analyst' not in blob and blob[:4] == b'CCV1'
    # Revoke: the next seal no longer contains the user.
    assert v.remove_user('Reviewer')
    ring = v.seal(master, data_dir=data, out_dir=out)
    assert ring['changed'] == [] and len(ring['users']) == 1
    with pytest.raises(v.VaultError):
        v.verify_login('reviewer', 'Another-Strong-Pass-2026', out_dir=out)
    (data / 'jobs.json').unlink()
    assert 'jobs.json' in v.unseal(master, data_dir=data, out_dir=out)
    assert json.loads((data / 'jobs.json').read_text())['jobs'][0]['title'] == 'SOC Analyst'


def test_password_policy_and_users_file_has_no_secrets(env):
    root, master, *_ = env
    with pytest.raises(v.VaultError):
        v.add_user('a', 'short', master)
    v.add_user('ashik', 'correct horse battery staple', master)
    text = v.USERS.read_text()
    assert 'ashik' not in text and 'correct horse' not in text
    assert v.list_users(master)[0]['username'] == 'ashik'


def test_seal_requires_users(env):
    _, master, data, out = env
    with pytest.raises(v.VaultError):
        v.seal(master, data_dir=data, out_dir=out)


def test_built_site_contains_only_ciphertext(env, monkeypatch):
    root, master, data, out = env
    v.add_user('ashik', 'correct horse battery staple', master)
    v.seal(master, data_dir=data, out_dir=out)
    site = v.build_site(root / '_site', vault_dir=out)
    names = {p.relative_to(site).as_posix() for p in site.rglob('*') if p.is_file()}
    assert 'encrypted/keyring.json' in names and 'index.html' in names
    assert not any(n.startswith('data/') for n in names)
    assert "mode: 'vault'" in (site / 'config.js').read_text()
    assert (site / 'robots.txt').read_text().startswith('User-agent: *\nDisallow: /')
