"""Local server entry point, safety and offline refresh tests."""
import http.client
import json
import threading
import time
from http.server import ThreadingHTTPServer
from pathlib import Path

import pytest

from server.app import RefreshController, load_local_env, make_handler, public_path


@pytest.fixture
def local_server():
    controller = RefreshController(max_search_queries=0, max_career_pages=0)
    server = ThreadingHTTPServer(('127.0.0.1', 0), make_handler(controller))
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield server.server_address[1], controller
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


def request(port, method, path, body=None, headers=None):
    connection = http.client.HTTPConnection('127.0.0.1', port, timeout=3)
    connection.request(method, path, body=body, headers=headers or {})
    response = connection.getresponse()
    result = response.status, dict(response.getheaders()), response.read()
    connection.close()
    return result


def refresh_request(port, origin=None, header=True, data='{}'):
    headers = {'Content-Type': 'application/json'}
    if header:
        headers['X-CyberCareers-Action'] = 'refresh'
    if origin:
        headers['Origin'] = origin
    return request(port, 'POST', '/api/refresh', data, headers)


def test_static_site_and_local_api(local_server):
    port, _ = local_server
    code, headers, html = request(port, 'GET', '/')
    assert code == 200
    assert b'CyberCareers' in html
    assert b'refreshJobsButton' in html
    assert headers['X-Content-Type-Options'] == 'nosniff'
    for filename in ('/styles.css', '/app.js', '/assets/favicon.svg',
                     '/data/jobs.json', '/data/sources.json', '/data/status.json'):
        code, _, data = request(port, 'GET', filename + '?v=123')
        assert code == 200 and data
    code, _, data = request(port, 'GET', '/api/health')
    assert code == 200
    health = json.loads(data)
    assert health['ok'] and health['mode'] == 'local' and health['jobs_count'] >= 1
    code, _, data = request(port, 'GET', '/api/refresh/status')
    assert code == 200 and json.loads(data)['running'] is False
    code, _, data = request(port, 'HEAD', '/')
    assert code == 200 and data == b''


def test_private_files_and_traversal_are_blocked(local_server):
    port, _ = local_server
    for path in ('/.env', '/.env.example', '/collector/collect.py', '/server/app.py',
                 '/tests/test_server.py', '/README.md', '/.git/config',
                 '/%2e%2e/.env', '/data/%2e%2e/collector/collect.py',
                 '/data/ats.json', '/assets/../../.env'):
        code, _, _ = request(port, 'GET', path)
        assert code == 404, (path, code)
    code, _, _ = request(port, 'GET', '/', headers={'Host': 'hostile.example'})
    assert code == 403
    assert public_path('/collector/collect.py') is None
    assert public_path('/data/jobs.json') is not None


def test_refresh_requires_same_origin_browser_intent(local_server):
    port, _ = local_server
    code, _, _ = refresh_request(port, origin='https://hostile.example')
    assert code == 403
    code, _, _ = refresh_request(port, header=False)
    assert code == 403
    code, _, _ = refresh_request(port, data='{"command":"anything"}')
    assert code == 400
    code, _, _ = refresh_request(port, data='invalid')
    assert code == 400


def test_refresh_async_and_no_parallel_collector(local_server, monkeypatch):
    from collector import collect

    port, _ = local_server
    release = threading.Event()
    invoked = threading.Event()

    def offline_collector(**kwargs):
        assert kwargs['max_queries'] == 0
        invoked.set()
        assert release.wait(3)
        return {'updated_at': '2026-11-07T12:00:00+06:00',
                'jobs_count': 14, 'new_candidates': 0, 'queries_run': 0}

    monkeypatch.setattr(collect, 'run', offline_collector)
    try:
        code, _, data = refresh_request(port, origin=f'http://127.0.0.1:{port}')
        assert code == 202 and json.loads(data)['started'] is True
        assert invoked.wait(1)
        code, _, data = refresh_request(port)
        assert code == 409 and json.loads(data)['running'] is True
        release.set()
        for _ in range(40):
            code, _, data = request(port, 'GET', '/api/refresh/status')
            report = json.loads(data)
            if not report['running']:
                break
            time.sleep(0.05)
        assert report['running'] is False
        assert report['last_error'] is None
        assert report['last_result']['jobs_count'] == 14
    finally:
        release.set()


def test_dotenv_defaults_only_and_no_unexpected_keys(tmp_path, monkeypatch):
    config = tmp_path / '.env'
    config.write_text('REFRESH_INTERVAL_HOURS=1\nMAX_CAREER_PAGES=8\n'
                      'NOT_AN_ALLOWED_SETTING=whatever\n# ignored\n')
    monkeypatch.setenv('REFRESH_INTERVAL_HOURS', '2')
    monkeypatch.delenv('MAX_CAREER_PAGES', raising=False)
    load_local_env(config)
    assert __import__('os').environ['REFRESH_INTERVAL_HOURS'] == '2'
    assert __import__('os').environ['MAX_CAREER_PAGES'] == '8'
    assert 'NOT_AN_ALLOWED_SETTING' not in __import__('os').environ
