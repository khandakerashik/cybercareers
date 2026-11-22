"""Live source lifecycle: actual starts, concurrent work, snapshots and reruns."""
from __future__ import annotations

import json
import threading
from concurrent.futures import ThreadPoolExecutor

import pytest

from collector import collect as c, custom_feeds, email_alerts, free_feeds, search_apis, telemetry
from server import app as server


START = '2026-11-22T10:12:00+00:00'
END = '2026-11-22T10:12:05+00:00'
PRIOR = '2026-11-22T09:16:00+00:00'


def task(source_id, name=None, **fields):
    return {'source_id': source_id, 'name': name or source_id, 'sector': 'Test', 'mode': 'Test', **fields}


def result_callback(monitor):
    def received(outcome, jobs):
        monitor.completed(source_id=outcome['source_id'], name=outcome['name'],
                          sector=outcome.get('sector', 'Test'), mode=outcome.get('mode', 'Test'),
                          state=outcome.get('state', 'ok'), jobs=outcome.get('jobs_found', len(jobs)),
                          message=outcome.get('message', ''))
    def started(outcome):
        monitor.started(source_id=outcome['source_id'], name=outcome['name'],
                        sector=outcome.get('sector', 'Test'), mode=outcome.get('mode', 'Test'))
    received.started = started
    return received


def rows(monitor):
    return {row['id']: row for row in monitor.snapshot()['sources']}


@pytest.fixture
def clock(monkeypatch):
    value = [START]
    monkeypatch.setattr(telemetry, 'timestamp', lambda: value[0])
    monkeypatch.delenv('GITHUB_ACTIONS', raising=False)
    return value


def test_parallel_lifecycle_keeps_current_work_distinct_from_last_result(tmp_path, clock):
    updates = []
    monitor = telemetry.CollectionTelemetry(tmp_path, total=2, status_callback=updates.append)
    monitor.plan_sources([task('a', 'Bank A'), task('b', 'Bank B')])
    assert {row['state'] for row in rows(monitor).values()} == {'queued'}
    monitor.started(**task('a', 'Bank A'))
    monitor.started(**task('b', 'Bank B'))
    first_running = monitor.snapshot()
    assert {row['id'] for row in first_running['active_sources']} == {'a', 'b'}
    clock[0] = END
    monitor.completed(**task('a', 'Bank A'), state='ok', jobs=3, new_jobs=2)
    partial = monitor.snapshot()
    assert partial['last_checked'] == 'Bank A'
    assert partial['current_source'] == 'Bank B'
    assert [row['id'] for row in partial['active_sources']] == ['b']
    assert rows(monitor)['a']['duration_seconds'] == 5
    assert partial['updated_at'] == END and partial['checked'] == 1
    # Previously emitted nested snapshots must not change after future results.
    assert {row['state'] for row in first_running['sources']} == {'running'}
    assert any(len(update['active_sources']) == 2 for update in updates)
    monitor.completed(**task('b', 'Bank B'), state='partial', jobs=0, message='Some pages unreadable')
    monitor.finish()
    persisted = json.loads((tmp_path / 'progress.json').read_text())
    assert persisted['active_sources'] == [] and persisted['checked'] == persisted['total'] == 2
    assert persisted['completion_status'] == 'completed_with_issues'
    assert persisted['last_completed_at'] == END


def test_dynamic_planning_and_repeated_result_do_not_inflate_totals(tmp_path):
    monitor = telemetry.CollectionTelemetry(tmp_path, total=0)
    monitor.plan_sources([task('first'), task('first')])
    monitor.started(**task('first'))
    monitor.completed(**task('first'), state='ok', jobs=2)
    monitor.completed(**task('first'), state='ok', jobs=2)
    monitor.plan_sources([task('first'), task('new-ats')])
    assert monitor.progress['total'] == 2 and monitor.progress['checked'] == 1
    assert monitor.progress['jobs_found_this_run'] == 2
    assert rows(monitor)['first']['state'] == 'success'
    assert rows(monitor)['new-ats']['state'] == 'queued'
    assert len(monitor.health['sources']['first']['history']) == 1


def test_cached_and_legacy_results_never_fabricate_start_time(tmp_path):
    monitor = telemetry.CollectionTelemetry(tmp_path, total=2)
    monitor.plan_sources([task('cached'), task('legacy')])
    monitor.completed(**task('cached'), state='cached')
    monitor.completed(**task('legacy'), state='ok')
    assert rows(monitor)['cached']['state'] == 'skipped'
    assert rows(monitor)['cached']['started_at'] is None
    assert rows(monitor)['legacy']['started_at'] is None
    assert rows(monitor)['legacy']['duration_seconds'] is None
    assert 'cached' not in monitor.health['sources']


def test_observer_failures_and_mutations_cannot_break_or_corrupt_collection(tmp_path):
    def broken(snapshot):
        snapshot['sources'].append({'id': 'corrupt', 'state': 'running'})
        raise RuntimeError('Publisher is unavailable')
    monitor = telemetry.CollectionTelemetry(tmp_path, total=1, status_callback=broken)
    monitor.plan_sources([task('real')])
    monitor.started(**task('real'))
    monitor.completed(**task('real'), state='ok')
    monitor.finish()
    assert set(rows(monitor)) == {'real'}
    assert monitor.progress['completion_status'] == 'completed'
    snapshot = monitor.snapshot()
    snapshot['sources'][0]['message'] = 'mutated by consumer'
    assert rows(monitor)['real']['message'] != 'mutated by consumer'


def test_interrupted_sources_stop_running_but_queued_sources_are_not_counted_as_fetched(tmp_path, clock):
    (tmp_path / 'status.json').write_text(json.dumps({'last_completed_at': PRIOR}))
    monitor = telemetry.CollectionTelemetry(tmp_path, total=2)
    monitor.plan_sources([task('started'), task('unattempted')])
    monitor.started(**task('started'))
    clock[0] = END
    monitor.finish(error='Stopped unexpectedly')
    assert rows(monitor)['started']['state'] == 'failed'
    assert rows(monitor)['unattempted']['state'] == 'queued'
    assert monitor.progress['active_sources'] == []
    assert monitor.progress['checked'] == 1 and monitor.progress['remaining'] == 1
    assert monitor.progress['last_completed_at'] == PRIOR
    assert monitor.progress['errors'] == ['Stopped unexpectedly']


class Response:
    status_code = 200
    headers = {}
    def __init__(self, data=None, content=b''):
        self.data, self.content = data, content
    def json(self): return self.data
    def raise_for_status(self): pass


def test_public_feed_announces_running_before_its_network_call(tmp_path, monkeypatch):
    monkeypatch.setattr(free_feeds, 'PROVIDERS', {'Remotive': {'url': 'https://remotive.com/api/remote-jobs', 'seconds': 3600}})
    monitor = telemetry.CollectionTelemetry(tmp_path, total=1)
    monitor.plan_sources([task('feed:Remotive')])
    class Session:
        def get(self, url, **kwargs):
            assert rows(monitor)['feed:Remotive']['state'] == 'running'
            assert monitor.progress['checked'] == 0
            return Response({'jobs': []})
    _, outcomes, _ = free_feeds.collect_public_feeds(Session(), [], {}, on_source=result_callback(monitor))
    assert outcomes[0]['state'] == 'ok'
    assert rows(monitor)['feed:Remotive']['state'] == 'success'


def test_custom_feed_cached_and_running_sources_are_reported_honestly(tmp_path):
    feeds = [{'url': 'https://example.org/jobs.xml', 'name': 'Due feed'},
             {'url': 'https://example.org/cached.xml', 'name': 'Cached feed'}]
    monitor = telemetry.CollectionTelemetry(tmp_path, total=2)
    monitor.plan_sources([task('custom:' + feed['url']) for feed in feeds])
    class Session:
        def get(self, url, **kwargs):
            assert url == feeds[0]['url']
            assert rows(monitor)['custom:' + url]['state'] == 'running'
            return Response(content=b'<rss><channel/></rss>')
    _, outcomes, _ = custom_feeds.collect_custom_feeds(Session(), feeds,
        {'custom:' + feeds[1]['url']: {'next_check': 200}}, [], clock=100, on_source=result_callback(monitor))
    assert [item['state'] for item in outcomes] == ['ok', 'cached']
    assert rows(monitor)['custom:' + feeds[1]['url']]['started_at'] is None


def test_mailbox_announces_running_before_imap_access(tmp_path, monkeypatch):
    monkeypatch.setattr(email_alerts, 'configured', lambda: True)
    monitor = telemetry.CollectionTelemetry(tmp_path, total=1)
    monitor.plan_sources([task('email:alerts')])
    def mailbox(**kwargs):
        assert rows(monitor)['email:alerts']['state'] == 'running'
        kwargs['diagnostics']['messages_read'] = 0
        return []
    monkeypatch.setattr(email_alerts, 'fetch_alert_rows', mailbox)
    email_alerts.collect_email_alerts([], on_source=result_callback(monitor))
    assert rows(monitor)['email:alerts']['state'] == 'success'


@pytest.mark.parametrize('provider', ['brave', 'jooble'])
def test_search_adapters_announce_running_before_requests(tmp_path, monkeypatch, provider):
    monitor = telemetry.CollectionTelemetry(tmp_path, total=1)
    source_id = 'api:' + provider
    monitor.plan_sources([task(source_id)])
    monkeypatch.setenv(provider.upper() + '_API_KEY', 'fixture-key')
    monkeypatch.setenv('JOOBLE_API_HOST', 'jooble.org')
    monkeypatch.setattr(search_apis.time, 'sleep', lambda _: None)
    class Session:
        def get(self, url, **kwargs):
            assert rows(monitor)[source_id]['state'] == 'running'
            return Response({'web': {'results': []}})
        def post(self, url, **kwargs):
            assert rows(monitor)[source_id]['state'] == 'running'
            return Response({'jobs': [], 'totalCount': 0})
    fn = search_apis.brave_search if provider == 'brave' else search_apis.jooble_search
    fn(Session(), {}, [], per_run=1, on_source=result_callback(monitor))
    assert rows(monitor)[source_id]['state'] == 'success'


def test_parallel_employers_are_active_together_before_fetch_returns(tmp_path, monkeypatch):
    monkeypatch.delenv('RENDER_JS', raising=False)
    sources = [{'id': str(i), 'name': f'Bank {i}', 'sector': 'Banking', 'mode': 'career',
                'website': f'https://bank{i}.example', 'careers_url': f'https://bank{i}.example/careers'}
               for i in range(2)]
    monitor = telemetry.CollectionTelemetry(tmp_path, total=2)
    monitor.plan_sources([task(src['id'], src['name']) for src in sources])
    barrier = threading.Barrier(2)
    observed = []
    class Fetcher:
        failures = {}
        discovered_ats = []
        ats_redirects = {}
        def fetch(self, url, **kwargs):
            barrier.wait(timeout=3)
            observed.append({row['id'] for row in monitor.snapshot()['active_sources']})
            barrier.wait(timeout=3)
            return '<html><body><h1>Careers</h1><p>No vacancies available.</p></body></html>'
    _, outcomes = c.coverage_round(sources, Fetcher(), 2, detail_budget=0, workers=2,
                                   on_source=result_callback(monitor))
    assert observed == [{'0', '1'}, {'0', '1'}]
    assert len(outcomes) == 2 and monitor.progress['checked'] == 2
    assert monitor.progress['active_sources'] == []


def test_real_run_queues_known_tasks_and_adds_discovered_ats_before_network(tmp_path, monkeypatch):
    monkeypatch.setattr(c, 'DATA', tmp_path)
    monkeypatch.delenv('ALERT_IMAP_USER', raising=False)
    monkeypatch.delenv('ALERT_IMAP_PASSWORD', raising=False)
    monkeypatch.delenv('BRAVE_API_KEY', raising=False)
    monkeypatch.delenv('JOOBLE_API_KEY', raising=False)
    monkeypatch.delenv('RENDER_JS', raising=False)
    monkeypatch.setattr(free_feeds, 'PROVIDERS', {'Remotive': {'url': 'https://remotive.com/api/remote-jobs', 'seconds': 3600}})
    source = {'id': 'bank', 'name': 'Example Bank', 'sector': 'Banking', 'mode': 'career',
              'website': 'https://bank.example', 'careers_url': 'https://bank.example/careers'}
    (tmp_path / 'sources.json').write_text(json.dumps([source]))
    updates = []
    def active(source_id):
        assert updates and source_id in {row['id'] for row in updates[-1]['active_sources']}
    class Session:
        def __init__(self): self.headers = {}
        def get(self, url, **kwargs):
            active('feed:Remotive' if 'remotive' in url else 'ats:greenhouse:fixturebank')
            return Response({'jobs': []})
        def close(self): pass
    class Fetcher:
        def __init__(self, *args):
            self.failures, self.discovered_ats, self.ats_redirects = {}, [], {}
        def fetch(self, url, **kwargs):
            active('bank')
            return ('<html><body><h1>Careers</h1><p>No vacancies available.</p>'
                    '<a href="https://boards.greenhouse.io/fixturebank">All vacancies</a></body></html>')
    monkeypatch.setattr(c.requests, 'Session', Session)
    monkeypatch.setattr(c, 'CompliantFetcher', Fetcher)
    report = c.run(max_queries=0, max_career_pages=1, max_detail_pages=0, on_progress=updates.append)
    first_plan = next(update for update in updates if update['sources'])
    assert {row['id'] for row in first_plan['sources']} == {'bank', 'feed:Remotive'}
    assert all(row['state'] == 'queued' for row in first_plan['sources'])
    final = report['progress_summary']
    assert final['checked'] == final['total'] == 3
    assert {row['id'] for row in final['sources']} == {'bank', 'feed:Remotive', 'ats:greenhouse:fixturebank'}
    assert all(row['started_at'] and row['finished_at'] for row in final['sources'])
    assert final['active_sources'] == []
    assert report['last_completed_at']


def test_local_restart_clears_stale_run_counters_and_returns_independent_snapshots(tmp_path, monkeypatch):
    data = tmp_path / 'data'
    data.mkdir()
    stale = {'running': False, 'checked': 25, 'total': 25, 'remaining': 0,
             'succeeded': 20, 'failed': 3, 'partial': 1, 'skipped': 1, 'new_jobs': 7,
             'jobs_found_this_run': 40, 'finished_at': PRIOR, 'last_completed_at': PRIOR,
             'last_successful_at': PRIOR, 'errors': ['Previous error'],
             'sources': [{'id': 'old', 'state': 'success'}], 'active_sources': [], 'last_checked': 'old'}
    (data / 'progress.json').write_text(json.dumps(stale))
    monkeypatch.setattr(server, 'ROOT', tmp_path)
    controller = server.RefreshController(refresh_every_hours=0)
    entered, release = threading.Event(), threading.Event()
    calls = []
    def collector(**kwargs):
        calls.append(1)
        entered.set()
        assert release.wait(3)
        return {'jobs_count': 0}
    monkeypatch.setattr(c, 'run', collector)
    try:
        with ThreadPoolExecutor(max_workers=8) as pool:
            starts = list(pool.map(lambda _: controller.start(), range(8)))
        assert starts.count(True) == 1 and len(calls) == 1 and entered.is_set()
        snapshot = controller.status()
        progress = snapshot['progress']
        assert snapshot['finished_at'] is None
        assert all(progress[key] == 0 for key in ('checked', 'total', 'remaining', 'succeeded', 'failed', 'partial',
                                                   'skipped', 'jobs_found_this_run', 'new_jobs'))
        assert progress['sources'] == progress['active_sources'] == []
        assert progress['last_completed_at'] == progress['last_successful_at'] == PRIOR
        assert progress['previous_errors'] == ['Previous error']
        progress['previous_errors'].append('external mutation')
        assert controller.status()['progress']['previous_errors'] == ['Previous error']
        incoming = {**progress, 'sources': [{'id': 'now', 'state': 'running'}]}
        controller._handle_progress(incoming)
        incoming['sources'][0]['state'] = 'failed'
        assert controller.status()['progress']['sources'][0]['state'] == 'running'
    finally:
        release.set()
