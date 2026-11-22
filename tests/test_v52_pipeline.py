"""Durable completion semantics and interrupted revalidation; no live network."""
from __future__ import annotations

import copy
import json
from datetime import datetime, timezone

import pytest

from collector import collect as c, email_alerts, free_feeds, search_apis, telemetry
from server import app as server


PRIOR = '2026-11-22T06:15:00+00:00'
START = '2026-11-22T07:12:00+00:00'
FINISH = '2026-11-22T07:16:30+00:00'


def read(path):
    return json.loads(path.read_text(encoding='utf-8'))


def write(path, data):
    path.write_text(json.dumps(data), encoding='utf-8')


def completed_source(monitor, source_id, state='ok'):
    monitor.completed(source_id=source_id, name=source_id, sector='Test', mode='Test', state=state)


@pytest.fixture
def clock(monkeypatch):
    value = [START]
    monkeypatch.setattr(telemetry, 'timestamp', lambda: value[0])
    monkeypatch.delenv('GITHUB_ACTIONS', raising=False)
    return value


def test_completed_scan_and_last_success_are_distinct_and_survive_restart(tmp_path, clock):
    write(tmp_path / 'status.json', {'last_completed_at': PRIOR, 'last_successful_at': PRIOR})
    monitor = telemetry.CollectionTelemetry(tmp_path, total=3)
    assert monitor.progress['last_completed_at'] == PRIOR
    completed_source(monitor, 'healthy')
    completed_source(monitor, 'not-due', 'cached')
    completed_source(monitor, 'blocked', 'error')
    clock[0] = FINISH
    monitor.finish()
    persisted = read(tmp_path / 'progress.json')
    assert persisted['completion_status'] == 'completed_with_issues'
    assert persisted['last_completed_at'] == FINISH
    assert persisted['last_successful_at'] == PRIOR
    assert persisted['duration_seconds'] == 270
    assert persisted['checked'] == 3 and persisted['remaining'] == 0
    health = read(tmp_path / 'source_health.json')['sources']
    assert 'not-due' not in health  # A cached result did not become a fake successful check.
    assert health['blocked']['last_result'] == 'failed'
    restarted = telemetry.CollectionTelemetry(tmp_path, total=1)
    assert restarted.progress['last_completed_at'] == FINISH
    assert restarted.progress['last_successful_at'] == PRIOR
    assert restarted.progress['finished_at'] is None


@pytest.mark.parametrize('prior', [None, PRIOR])
@pytest.mark.parametrize('failure', ['incomplete', 'exception'])
def test_unfinished_runs_never_invent_a_completion_time(tmp_path, clock, prior, failure):
    # updated_at is a dataset timestamp, not proof of a completed collection.
    write(tmp_path / 'status.json', {'updated_at': PRIOR, 'last_completed_at': prior,
                                    'last_successful_at': prior})
    monitor = telemetry.CollectionTelemetry(tmp_path, total=2)
    completed_source(monitor, 'first')
    clock[0] = FINISH
    monitor.finish(error='Collector interrupted' if failure == 'exception' else '')
    status = read(tmp_path / 'progress.json')
    assert status['finished_at'] == FINISH
    assert status['running'] is False
    assert status['last_completed_at'] == prior
    assert status['last_successful_at'] == prior
    assert status['completion_status'] == ('failed' if failure == 'exception' else 'incomplete')
    assert status['remaining'] == 1


def test_successful_zero_jobs_is_a_completed_scan(tmp_path, clock):
    monitor = telemetry.CollectionTelemetry(tmp_path, total=1)
    completed_source(monitor, 'empty-but-readable')
    clock[0] = FINISH
    monitor.finish()
    persisted = read(tmp_path / 'progress.json')
    assert persisted['jobs_found_this_run'] == 0
    assert persisted['last_completed_at'] == persisted['last_successful_at'] == FINISH
    assert persisted['completion_status'] == 'completed'


def test_scheduler_does_not_claim_cli_is_hourly(monkeypatch):
    monkeypatch.delenv('GITHUB_ACTIONS', raising=False)
    at = datetime(2026, 11, 22, 7, 12, tzinfo=timezone.utc)
    manual = telemetry.collection_schedule(at)
    assert manual['enabled'] is False and manual['next_scheduled_at'] is None
    monkeypatch.setenv('GITHUB_ACTIONS', 'true')
    hourly = telemetry.collection_schedule(at)
    assert hourly['enabled'] is True and hourly['interval_minutes'] == 60
    assert hourly['next_scheduled_at'] == '2026-11-22T08:12:00+00:00'


@pytest.fixture
def offline_run(tmp_path, monkeypatch, clock):
    monkeypatch.setattr(c, 'DATA', tmp_path)
    monkeypatch.setattr(email_alerts, 'configured', lambda: False)
    monkeypatch.setattr(search_apis, 'configured_count', lambda: 0)
    monkeypatch.setattr(c, 'coverage_round', lambda *args, **kwargs: ([], []))
    monkeypatch.setattr(c, 'ats_jobs', lambda *args, **kwargs: ([], []))
    monkeypatch.setattr(c.requests.Session, 'request',
                        lambda *args, **kwargs: pytest.fail('Offline pipeline test attempted network access'))
    write(tmp_path / 'sources.json', [])
    write(tmp_path / 'status.json', {'last_completed_at': PRIOR, 'last_successful_at': PRIOR})
    valid = c.new_job(title='SOC Analyst', company='Example Bank', source='Official employer',
                      url='https://bank.example/jobs/100', sources=[],
                      posted='2020-01-01', deadline='2020-02-01',
                      description='Review SOC alerts and suspicious activity for the bank.')
    valid.update(collected_at='2020-01-01', last_seen_at='2020-01-02')
    invalid = c.new_job(title='SOC Analyst Training', company='Example Academy', source='Official employer',
                        url='https://academy.example/careers/training', sources=[],
                        description='Register now for a cybersecurity workshop. Course fee BDT 500.')
    write(tmp_path / 'jobs.json', {'jobs': [valid, invalid]})

    def install_feeds(batch=(), *, state='ok'):
        def feeds(session, sources, saved_state, *, on_source, **kwargs):
            outcomes = []
            for i, name in enumerate(free_feeds.PROVIDERS):
                rows = list(batch) if i == 0 else []
                outcome = {'source_id': 'feed:' + name, 'name': name, 'sector': 'Remote job feed',
                           'mode': 'Free publisher feed', 'state': state, 'jobs_found': len(rows)}
                on_source(outcome, rows)
                outcomes.append(outcome)
            clock[0] = FINISH
            return list(batch), outcomes, saved_state
        monkeypatch.setattr(free_feeds, 'collect_public_feeds', feeds)

    install_feeds()
    return {'path': tmp_path, 'valid': copy.deepcopy(valid), 'invalid': copy.deepcopy(invalid),
            'feeds': install_feeds}


def test_successful_pipeline_quarantines_false_events_without_deleting_real_history(offline_run):
    report = c.run(max_queries=0, max_career_pages=0, max_detail_pages=0)
    directory = offline_run['path']
    jobs = read(directory / 'jobs.json')['jobs']
    assert len(jobs) == 1
    for field in ('id', 'title', 'description', 'source_url', 'posted_at', 'deadline',
                  'collected_at', 'last_seen_at'):
        assert jobs[0][field] == offline_run['valid'][field]
    assert jobs[0]['vacancy_status'] == 'expired'
    rejected = read(directory / 'rejected_jobs.json')['records']
    assert len(rejected) == 1 and rejected[0]['job'] == offline_run['invalid']
    assert rejected[0]['previously_published'] is True
    assert report['detection']['prior_records_quarantined'] == 1
    assert report['last_completed_at'] == FINISH
    assert report['last_successful_at'] == FINISH
    assert read(directory / 'status.json')['last_completed_at'] == FINISH


def test_later_stage_failure_preserves_quarantine_and_incremental_real_jobs(offline_run, monkeypatch):
    directory = offline_run['path']
    new_valid = c.new_job(title='Information Security Officer', company='Second Bank', sources=[],
        source='Official employer', url='https://second.example/jobs/20',
        description='Responsibilities: maintain the ISMS. Requirements: degree. Full-time. Apply now.')
    new_invalid = c.new_job(title='Information Security Webinar', company='Academy', sources=[],
        source='Official employer', url='https://academy.example/careers/webinar',
        description='Register here for our information security webinar.')
    offline_run['feeds']([new_valid, new_invalid])

    def fail_after_incremental_save(*args, **kwargs):
        # This executes before the pipeline's exception/finally handlers.
        persisted = read(directory / 'jobs.json')['jobs']
        assert {job['title'] for job in persisted} == {'SOC Analyst', 'Information Security Officer'}
        already_saved = read(directory / 'rejected_jobs.json')['records']
        assert any(row['job'] == offline_run['invalid'] for row in already_saved)
        raise RuntimeError('Simulated downstream parser failure')

    monkeypatch.setattr(c, 'coverage_round', fail_after_incremental_save)
    with pytest.raises(RuntimeError, match='downstream'):
        c.run(max_queries=0, max_career_pages=0, max_detail_pages=0)
    rejected = read(directory / 'rejected_jobs.json')['records']
    by_title = {row['job']['title']: row for row in rejected}
    assert set(by_title) == {'SOC Analyst Training', 'Information Security Webinar'}
    assert by_title['SOC Analyst Training']['previously_published'] is True
    assert by_title['Information Security Webinar']['previously_published'] is False
    persisted = read(directory / 'jobs.json')['jobs']
    assert len(persisted) == 2
    original = next(row for row in persisted if row['id'] == offline_run['valid']['id'])
    assert original['posted_at'] == '2020-01-01' and original['last_seen_at'] == '2020-01-02'
    for filename in ('status.json', 'progress.json'):
        state = read(directory / filename)
        assert state['completion_status'] == 'failed'
        assert state['last_completed_at'] == PRIOR and state['last_successful_at'] == PRIOR
    assert read(directory / 'progress.json')['finished_at'] == FINISH


def test_failure_after_finish_does_not_publish_a_fake_completed_timestamp(offline_run, monkeypatch):
    original_write = c.write_json
    failed = []
    def fail_final_status_once(path, payload):
        if path.name == 'status.json' and payload.get('completion_status') == 'completed' and not failed:
            failed.append(True)
            raise OSError('Simulated final status write failure')
        original_write(path, payload)
    monkeypatch.setattr(c, 'write_json', fail_final_status_once)
    with pytest.raises(OSError, match='final status'):
        c.run(max_queries=0, max_career_pages=0, max_detail_pages=0)
    assert failed
    for filename in ('progress.json', 'status.json'):
        state = read(offline_run['path'] / filename)
        assert state['completion_status'] == 'failed'
        assert state['last_completed_at'] == PRIOR
        assert state['last_successful_at'] == PRIOR


def test_run_with_unreported_scheduled_targets_does_not_claim_completion(offline_run, monkeypatch):
    # A collector that returns without all target callbacks is incomplete,
    # even though the Python function itself returned normally.
    monkeypatch.setattr(free_feeds, 'collect_public_feeds', lambda *args, **kwargs: ([], [], {}))
    report = c.run(max_queries=0, max_career_pages=0, max_detail_pages=0)
    assert report['completion_status'] == 'incomplete'
    assert report['last_completed_at'] == PRIOR and report['last_successful_at'] == PRIOR
    assert report['progress_summary']['remaining'] == len(free_feeds.PROVIDERS)


def test_process_restart_marks_stale_worker_interrupted_and_keeps_last_completion(tmp_path, monkeypatch):
    data = tmp_path / 'data'
    data.mkdir()
    write(data / 'progress.json', {'running': True, 'phase': 'employers',
          'last_completed_at': PRIOR, 'started_at': START, 'finished_at': None})
    monkeypatch.setattr(server, 'ROOT', tmp_path)
    controller = server.RefreshController(refresh_every_hours=0)
    snapshot = controller.status()
    assert snapshot['running'] is False and snapshot['progress']['running'] is False
    assert snapshot['progress']['completion_status'] == 'interrupted'
    assert snapshot['progress']['last_completed_at'] == PRIOR
    assert snapshot['progress']['finished_at'] is None
    assert snapshot['progress']['schedule']['enabled'] is False


def test_old_alert_not_rejuvenated_by_incremental_store(tmp_path):
    from collector.collect import new_job
    from collector.telemetry import IncrementalJobStore
    job=new_job(title='SOC Analyst',company='Bank',url='https://www.linkedin.com/jobs/view/1234567890/',
                source='LinkedIn alert email',sources=[],verification_level='Email alert (subscribed)')
    job.update(last_seen_at='2026-01-01',last_observed_at='2026-01-01',alert_received_at='2026-01-01')
    store=IncrementalJobStore(tmp_path/'jobs.json')
    store.merge_batch([job])
    assert store.jobs[0]['last_seen_at']=='2026-01-01'
    assert store.jobs[0]['last_observed_at']=='2026-01-01'


def test_two_pdf_roles_survive_a_download_url_without_pdf_suffix():
    common={'company':'Bank','url':'https://bank.example/download?id=123',
            'source':'Official PDF circular','sources':[],
            'description':'Recruitment circular. Submit your CV to apply.'}
    records=[c.new_job(title=title,**common) for title in ('SOC Analyst','Information Security Officer')]
    assert len(c.deduplicate(records))==2
    assert len({job['id'] for job in records})==2
