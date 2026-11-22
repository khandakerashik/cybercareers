"""Offline protocol, privacy, coalescing and deployment checks for live progress."""
import base64
import copy
import gzip
import json
import secrets
import threading
from pathlib import Path

import pytest
import requests
from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

import vault
from collector import github_progress as gp


UID = 'a' * 64
REPO = 'ExampleOwner/cybercareers'
RUN = '123456789'
SHA = 'a' * 40


@pytest.fixture
def crypto_context():
    master, kek = secrets.token_bytes(32), secrets.token_bytes(32)
    users = {UID: {'kek_escrow': vault.seal_bytes(master, kek, 'cc-escrow:' + UID)}}
    return master, kek, users


def encoder(context):
    master, _, users = context
    return gp.LiveProgressEncoder(REPO, RUN, 2, master, users)


def unpack(text, kek, *, run=RUN, attempt=2, repository=REPO):
    marker, payload = text.split('\n', 1)
    assert marker == gp.FORMAT
    envelope = json.loads(base64.b64decode(payload, validate=True))
    context = f'{repository}:{run}:{attempt}'
    key = vault.open_bytes(kek, envelope['users'][UID], f'cc-live-key:{context}:{UID}')
    plain = vault.open_bytes(key, envelope, 'cc-live:' + context)
    return envelope, json.loads(gzip.decompress(plain)), key


def test_envelope_round_trip_contains_only_current_user_wrappers(crypto_context):
    value = {'running': True, 'current_source': 'Private employer name', 'checked': 3,
             'sources': [{'id': 'source-secret', 'state': 'running'}]}
    text = encoder(crypto_context).encode(value)
    envelope, result, _ = unpack(text, crypto_context[1])
    assert result == value
    assert envelope['format'] == 'CCLIVE1'
    assert envelope['repository'] == REPO
    assert envelope['workflow_run_id'] == RUN and envelope['run_attempt'] == 2
    assert set(envelope['users']) == {UID}
    assert set(envelope['users'][UID]) == {'iv', 'ct'}
    assert 'ci' not in envelope and 'salt' not in envelope['users'][UID]
    assert len(base64.b64decode(envelope['iv'])) == 12
    assert len(base64.b64decode(envelope['users'][UID]['ct'])) == 48
    assert 'Private employer name' not in text and 'source-secret' not in json.dumps(envelope)


@pytest.mark.parametrize('metadata', [
    {'run': '987654321'}, {'attempt': 1}, {'repository': 'other/repository'},
])
def test_ciphertext_cannot_be_replayed_into_another_run_context(crypto_context, metadata):
    text = encoder(crypto_context).encode({'running': True})
    with pytest.raises(InvalidTag):
        unpack(text, crypto_context[1], **metadata)


def test_fresh_run_key_and_fresh_snapshot_nonce(crypto_context):
    first = encoder(crypto_context)
    a, _, key_a = unpack(first.encode({'checked': 1}), crypto_context[1])
    b, _, key_b = unpack(first.encode({'checked': 1}), crypto_context[1])
    _, _, key_c = unpack(encoder(crypto_context).encode({'checked': 1}), crypto_context[1])
    assert key_a == key_b and key_a != key_c
    assert a['iv'] != b['iv'] and a['ct'] != b['ct']


def test_all_normal_source_rows_fit_without_truncation(crypto_context):
    progress = {'running': True, 'checked': 125, 'total': 250,
                'sources': [{'id': f'source-{n}', 'name': f'Employer {n}', 'state': 'queued' if n > 125 else 'success',
                             'message': 'Public career page checked', 'jobs_found': n % 3} for n in range(250)]}
    text = encoder(crypto_context).encode(progress)
    assert len(text) <= 65_000
    _, restored, _ = unpack(text, crypto_context[1])
    assert restored == progress


def test_oversized_detail_is_compacted_with_explicit_coverage_metadata(crypto_context):
    rows = [{'id': f'source-{n}', 'state': 'success', 'name': f'Employer {n}',
             'message': secrets.token_hex(1000)} for n in range(600)]
    progress = {'running': True, 'checked': 599, 'total': 600, 'sources': rows,
                'active_sources': [{'id': 'still-running', 'state': 'running'}]}
    text = encoder(crypto_context).encode(progress)
    _, restored, _ = unpack(text, crypto_context[1])
    assert len(text) <= 65_000
    assert restored['checked'] == 599 and restored['total'] == 600
    assert restored['source_details_truncated']
    assert restored['source_rows_total'] == 600
    assert restored['source_rows_included'] == len(restored['sources'])
    assert restored['source_rows_truncated'] == (len(restored['sources']) < 600)
    assert restored['active_sources'][0]['id'] == 'still-running'


def test_encoder_never_silently_drops_configured_users(crypto_context):
    master, _, users = crypto_context
    too_many = {f'{n:064x}': users[UID] for n in range(101)}
    with pytest.raises(ValueError, match='100 configured'):
        gp.LiveProgressEncoder(REPO, RUN, 1, master, too_many)
    with pytest.raises(ValueError, match='repository'):
        gp.LiveProgressEncoder('https://hostile.example/repo', RUN, 1, master, users)


class Response:
    def __init__(self, data, status=200):
        self.data, self.status_code = data, status

    def json(self):
        return self.data


class Session:
    def __init__(self, block_first=False, status=200):
        self.calls = []
        self.entered = threading.Event()
        self.release = threading.Event()
        self.block_first = block_first
        self.status = status
        self.closed = False

    def request(self, method, url, **kwargs):
        self.calls.append((method, url, copy.deepcopy(kwargs)))
        self.entered.set()
        if self.block_first and len(self.calls) == 1:
            assert self.release.wait(3), 'Test did not release the mock HTTP request'
        return Response({'id': 42, 'check_runs': []}, self.status)

    def close(self):
        self.closed = True


def test_callbacks_coalesce_without_waiting_for_http_and_final_bypasses_throttle(crypto_context):
    session = Session(block_first=True)
    publisher = gp.GitHubProgressPublisher(encoder(crypto_context), 'synthetic-test-token', SHA,
                                           session=session, interval_seconds=600)
    initial = {'running': True, 'checked': 0, 'sources': [{'name': 'Original source'}]}
    publisher.publish(initial)
    assert session.entered.wait(1)
    initial['sources'][0]['name'] = 'Mutated after callback'
    returned = threading.Event()

    def many_callbacks():
        for n in range(1, 200):
            publisher.publish({'running': n != 199, 'checked': n,
                               'completion_status': 'completed' if n == 199 else 'running'})
        returned.set()

    submitter = threading.Thread(target=many_callbacks)
    submitter.start()
    try:
        assert returned.wait(1), 'Callbacks waited for a blocked GitHub request'
        assert len(session.calls) == 1
        finalizer = threading.Thread(target=publisher.finish)
        finalizer.start()
        session.release.set()
        finalizer.join(2)
        assert not finalizer.is_alive()
        assert len(session.calls) == 2
        first, final = session.calls
        assert first[0] == 'POST' and final[0] == 'PATCH'
        assert first[2]['json']['external_id'] == 'CCLIVE1:123456789:2'
        assert first[2]['json']['name'] == gp.CHECK_NAME
        assert unpack(first[2]['json']['output']['text'], crypto_context[1])[1]['sources'][0]['name'] == 'Original source'
        final_body = final[2]['json']
        assert final_body['status'] == 'completed' and final_body['conclusion'] == 'success'
        assert unpack(final_body['output']['text'], crypto_context[1])[1]['checked'] == 199
        assert all(call[1].startswith('https://api.github.com/repos/') for call in session.calls)
        assert all(call[2]['allow_redirects'] is False and call[2]['timeout'] == gp.REQUEST_TIMEOUT for call in session.calls)
        assert 'synthetic-test-token' not in json.dumps(final_body)
        assert session.closed
    finally:
        session.release.set()
        submitter.join(2)
        publisher.finish()


@pytest.mark.parametrize('status,conclusion', [
    ('completed_with_issues', 'neutral'), ('incomplete', 'failure'), ('failed', 'failure'),
])
def test_final_check_conclusion_reflects_collection_outcome(crypto_context, status, conclusion):
    session = Session()
    publisher = gp.GitHubProgressPublisher(encoder(crypto_context), 'test-token', SHA, session=session)
    publisher.publish({'running': False, 'completion_status': status})
    assert publisher.finish()
    assert session.calls[-1][2]['json']['conclusion'] == conclusion


def test_checks_errors_and_redirects_do_not_raise_or_follow_untrusted_hosts(crypto_context):
    session = Session(status=302)
    publisher = gp.GitHubProgressPublisher(encoder(crypto_context), 'test-token', SHA, session=session)
    publisher.publish({'running': True, 'checked': 0})
    assert not publisher.finish(error=True)
    assert publisher.last_error
    assert all(call[1].startswith(gp.API_ROOT + '/') and call[2]['allow_redirects'] is False for call in session.calls)


def test_timed_out_creation_recovers_existing_check_before_retry(crypto_context):
    class TimedOutCreation(Session):
        def request(self, method, url, **kwargs):
            self.calls.append((method, url, copy.deepcopy(kwargs)))
            if method == 'POST':
                self.entered.set()
                raise requests.Timeout('Synthetic timeout')
            if method == 'GET':
                return Response({'check_runs': [{'id': 88, 'name': gp.CHECK_NAME,
                                  'external_id': 'CCLIVE1:123456789:2', 'head_sha': SHA}]})
            return Response({'id': 88})
    session = TimedOutCreation()
    publisher = gp.GitHubProgressPublisher(encoder(crypto_context), 'test-token', SHA, session=session)
    publisher.publish({'running': True})
    assert session.entered.wait(1)
    assert publisher.finish(error=True)
    assert [call[0] for call in session.calls] == ['POST', 'GET', 'PATCH']
    assert session.calls[-1][1].endswith('/check-runs/88')


def test_unconfigured_publisher_never_reads_a_key_or_uses_network(monkeypatch):
    monkeypatch.setattr(vault, 'load_master', lambda: pytest.fail('A key must not be read'))
    publisher = gp.publisher_from_environment({'GITHUB_ACTIONS': 'true'})
    assert not publisher.enabled
    publisher.publish({'running': True})
    assert not publisher.finish()


def test_cli_keeps_existing_arguments_and_optional_finalize_failure_is_not_fatal(monkeypatch, capsys):
    from collector import collect
    from server import app
    monkeypatch.setattr(app, 'load_local_env', lambda: None)
    class OptionalFailure(gp.NullPublisher):
        def finish(self, **kwargs):
            raise RuntimeError('Synthetic optional telemetry failure')
    monkeypatch.setattr(gp, 'publisher_from_environment', lambda: OptionalFailure())
    def run(*args, **kwargs):
        assert args == (2, 30, 80, False)
        assert kwargs['force_feeds'] is True
        kwargs['on_progress']({'running': False, 'completion_status': 'completed'})
        return {'jobs_count': 4}
    monkeypatch.setattr(collect, 'run', run)
    assert gp.main(['--max-search-queries', '2', '--max-career-pages', '30', '--max-detail-pages', '80', '--force-feeds']) == 0
    assert json.loads(capsys.readouterr().out)['jobs_count'] == 4


def test_cli_dry_run_does_not_create_a_check(monkeypatch, capsys):
    from collector import collect
    from server import app
    monkeypatch.setattr(app, 'load_local_env', lambda: None)
    monkeypatch.setattr(gp, 'publisher_from_environment', lambda: pytest.fail('Dry run must not create checks'))
    monkeypatch.setattr(collect, 'run', lambda *args, **kwargs: {'dry_run': args[3]})
    assert gp.main(['--dry-run']) == 0
    assert json.loads(capsys.readouterr().out)['dry_run'] is True


def test_public_build_metadata_is_explicit_and_excludes_tokens():
    environment = {'GITHUB_REPOSITORY': REPO, 'GITHUB_REF_TYPE': 'branch', 'GITHUB_REF_NAME': 'release/live',
                   'GITHUB_DEFAULT_BRANCH': 'main', 'GH_PROGRESS_TOKEN': 'private', 'CC_MASTER_KEY': 'private-key'}
    assert vault.github_site_config(environment) == {'repository': REPO, 'workflow': 'pages.yml', 'ref': 'release/live'}
    assert vault.github_site_config({}) is None
    assert vault.github_site_config({'GITHUB_REPOSITORY': REPO}) is None
    assert vault.github_site_config({'GITHUB_REPOSITORY': 'https://evil.example/owner/repo', 'GITHUB_DEFAULT_BRANCH': 'main'}) is None
    assert vault.github_site_config({'GITHUB_REPOSITORY': REPO, 'GITHUB_REF_TYPE': 'tag', 'GITHUB_REF_NAME': 'v5.4',
                                    'GITHUB_DEFAULT_BRANCH': 'main'})['ref'] == 'main'


def test_workflow_and_asset_shipping_use_the_live_protocol():
    from server.app import public_path
    root = Path(__file__).resolve().parents[1]
    workflow = (root / '.github/workflows/pages.yml').read_text()
    assert '  checks: write\n' in workflow
    assert 'python -m collector.ci' in workflow
    assert workflow.count('GH_PROGRESS_TOKEN: ${{ github.token }}') == 1
    collect_block = workflow.split('id: collect', 1)[1].split('- name: Encrypt', 1)[0]
    assert 'GH_PROGRESS_TOKEN: ${{ github.token }}' in collect_block
    assert "- 'github-scan.js'" in workflow
    assert 'github-scan.js' in vault.SITE_FILES
    assert public_path('/github-scan.js') == root / 'github-scan.js'
    assert public_path('/collector/github_progress.py') is None
