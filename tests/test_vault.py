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


def test_application_module_ships_but_personal_backups_do_not(env,monkeypatch):
    root,master,data,out=env
    private='A private application note that must stay on this computer'
    (data/'applications.json').write_text(json.dumps({'notes':private}))
    v.add_user('ashik','correct horse battery staple',master)
    ring=v.seal(master,data_dir=data,out_dir=out)
    assert 'applications.json' not in ring['files']
    assert not (out/'applications.bin').exists()
    (out/'application-notes.txt').write_text(private)
    (out/'unused-backup.bin').write_text(private)
    ui=root/'ui'
    (ui/'assets').mkdir(parents=True)
    (ui/'index.html').write_text('<script type="module" src="app.js"></script>')
    (ui/'app.js').write_text("import './applications.js';")
    module='export const applicationModuleLoaded = true;'
    (ui/'applications.js').write_text(module)
    (ui/'assets'/'favicon.svg').write_text('<svg xmlns="http://www.w3.org/2000/svg"/>')
    (ui/'assets'/'applications.csv').write_text(private)
    (ui/'applications.json').write_text(json.dumps({'notes':private}))
    monkeypatch.setattr(v,'ROOT',ui)
    site=v.build_site(root/'_site',vault_dir=out)
    assert (site/'applications.js').read_text()==module
    assert (site/'assets'/'favicon.svg').is_file()
    assert (site/'encrypted'/'jobs.bin').is_file()
    assert (site/'encrypted'/'sources.bin').is_file()
    assert not (site/'assets'/'applications.csv').exists()
    assert not (site/'encrypted'/'unused-backup.bin').exists()
    assert all(private.encode() not in p.read_bytes() for p in site.rglob('*') if p.is_file())


def test_site_rejects_an_unexpected_ciphertext_manifest_path(env):
    root,master,data,out=env
    v.add_user('ashik','correct horse battery staple',master)
    v.seal(master,data_dir=data,out_dir=out)
    ring=json.loads((out/'keyring.json').read_text())
    ring['files']['jobs.json']['path']='../application-notes.txt'
    (out/'keyring.json').write_text(json.dumps(ring))
    with pytest.raises(v.VaultError,match='unexpected encrypted file'):
        v.build_site(root/'_site',vault_dir=out)


def test_build_ships_scan_module_and_only_public_github_configuration(env,monkeypatch):
    root,master,data,out=env
    v.add_user('ashik','correct horse battery staple',master)
    v.seal(master,data_dir=data,out_dir=out)
    monkeypatch.setenv('GITHUB_REPOSITORY','ExampleOwner/cybercareers')
    monkeypatch.setenv('GITHUB_REF_TYPE','branch')
    monkeypatch.setenv('GITHUB_REF_NAME','release/live')
    monkeypatch.setenv('GH_PROGRESS_TOKEN','synthetic-private-progress-token')
    site=v.build_site(root/'_site',vault_dir=out)
    config=(site/'config.js').read_text()
    metadata=json.loads(config.split('github: ',1)[1].rsplit(' });',1)[0])
    assert metadata=={'repository':'ExampleOwner/cybercareers','workflow':'pages.yml','ref':'release/live'}
    assert 'synthetic-private-progress-token' not in config and 'CC_MASTER_KEY' not in config
    assert (site/'github-scan.js').is_file()
