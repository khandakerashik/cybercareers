"""Calendar-day archive semantics for Bangladesh and retained application leads."""
from __future__ import annotations

import copy
from datetime import datetime, timezone

import pytest

from collector import collect as c


@pytest.fixture
def bd_clock(monkeypatch):
    value = [datetime(2026, 11, 22, 12, 0, tzinfo=c.BANGLADESH)]
    monkeypatch.setattr(c, 'now_bd', lambda: value[0])
    return value


def role(**fields):
    return {'id': 'role-1', 'title': 'SOC Analyst', 'source': 'Official employer',
            'vacancy_status': 'unverified', 'last_seen_at': '2026-11-22', **fields}


def test_deadline_today_stays_open_until_end_of_bangladesh_day(bd_clock):
    today = role(deadline='2026-11-22')
    bd_clock[0] = datetime(2026, 11, 22, 23, 59, 59, tzinfo=c.BANGLADESH)
    result = c.annotate_freshness([today])[0]
    assert result['vacancy_status'] == 'unverified' and result['archive_reason'] == ''
    # This is 18:00 UTC on the previous UTC day: archive follows BDT midnight.
    bd_clock[0] = datetime(2026, 11, 22, 18, 0, tzinfo=timezone.utc)
    result = c.annotate_freshness([today])[0]
    assert result['vacancy_status'] == 'expired'
    assert result['archive_reason'] == 'deadline_passed'


@pytest.mark.parametrize(('raw', 'expected'), [
    ('2026-11-22', '2026-11-22'),
    ('2026-11-22T18:30:00Z', '2026-11-23'),
    ('2026-11-23T01:00:00+09:00', '2026-11-22'),
    ('2026-11-22T23:59:00-05:00', '2026-11-23'),
    ('২২ নভেম্বর ২০২৬', '2026-11-22'),
    ('2028-02-29', '2028-02-29'),
])
def test_deadline_dates_are_valid_and_normalised_to_bangladesh(raw, expected):
    assert c.deadline_date(raw) == expected


def test_unix_deadline_uses_bangladesh_calendar_date():
    instant = datetime(2026, 11, 22, 18, 30, tzinfo=timezone.utc)
    assert c.deadline_date(int(instant.timestamp())) == '2026-11-23'
    assert c.deadline_date(int(instant.timestamp() * 1000)) == '2026-11-23'


@pytest.mark.parametrize('invalid', [
    '', None, 'Not stated', '2026-02-29', '2026-02-31', '2026-13-01',
    '2026-11-22T25:61:00Z', {'date': '2020-01-01'}, True,
])
def test_invalid_deadline_is_unknown_and_cannot_expire_a_lead(bd_clock, invalid):
    assert c.deadline_date(invalid) == ''
    result = c.annotate_freshness([role(deadline=invalid)])[0]
    assert result['vacancy_status'] == 'unverified'
    assert result['archive_reason'] == ''


def test_new_job_normalises_deadline_without_changing_publication_date_semantics(bd_clock):
    job = c.new_job(title='SOC Analyst', company='Bank', url='https://bank.example/jobs/1',
                    source='Official employer', sources=[], description='Review SIEM alerts.',
                    posted='2026-11-22T18:30:00Z', deadline='2026-11-22T18:30:00Z')
    assert job['deadline'] == '2026-11-23'
    assert job['posted_at'] == '2026-11-22'


def test_timestamp_deadline_uses_documented_whole_day_semantics(bd_clock):
    # An exact closing hour is not retained by the existing date-only model.
    bd_clock[0] = datetime(2026, 11, 23, 15, 0, tzinfo=c.BANGLADESH)
    job = role(deadline='2026-11-22T18:30:00Z')  # 00:30 on 23 November BDT.
    result = c.annotate_freshness([job])[0]
    assert result['deadline'] == '2026-11-23'
    assert result['vacancy_status'] != 'expired'


def test_old_publication_or_observation_dates_do_not_mean_expired(bd_clock):
    old_posting = role(posted_at='2020-01-01', last_seen_at='', collected_at='')
    old_observation = role(id='role-2', posted_at='2026-11-21', last_seen_at='2020-01-01')
    source_records = [old_posting, old_observation]
    original = copy.deepcopy(source_records)
    visible = c.live_filter(source_records, age_limit=45)
    assert len(visible) == 2
    assert all(job['vacancy_status'] == 'older_unverified' for job in visible)
    assert all(job['archive_reason'] == '' for job in visible)
    assert source_records == original  # Filtering does not rewrite caller-owned records.


def test_explicit_closed_and_undated_expired_records_stay_archived(bd_clock):
    records = [role(vacancy_status='closed', deadline='2026-12-30'),
               role(id='role-2', vacancy_status='expired', deadline='')]
    marked = c.annotate_freshness(records)
    assert len(marked) == 2
    assert [job['vacancy_status'] for job in marked] == ['closed', 'expired']
    assert [job['archive_reason'] for job in marked] == ['source_closed', 'source_expired']
    assert c.live_filter(marked, age_limit=45) == []


def test_future_or_today_deadline_clears_stale_derived_expired_status(bd_clock):
    records = [role(vacancy_status='expired', deadline=deadline, archive_reason='deadline_passed')
               for deadline in ('2026-11-22', '2026-12-01')]
    assert all(job['vacancy_status'] == 'unverified' for job in c.annotate_freshness(records))
    assert all(job['archive_reason'] == '' for job in records)


@pytest.mark.parametrize('previous_status', ['expired', 'closed'])
def test_fresh_official_deadline_extension_retains_identity_and_reopens_job(bd_clock, previous_status):
    options = {'title': 'SOC Analyst', 'company': 'Bank', 'url': 'https://bank.example/jobs/1',
               'source': 'Official employer', 'sources': [], 'verification_level': 'Official page parsed'}
    previous = c.new_job(**options, description='Earlier description. ' * 50,
                         deadline='2026-11-20', vacancy_status=previous_status)
    previous.update(last_seen_at='2026-11-20', last_observed_at='2026-11-20T00:00:00+06:00')
    latest = c.new_job(**options, description='Application deadline extended. Apply now.', deadline='2026-12-01')
    results = c.annotate_freshness(c.deduplicate([previous, latest]))
    assert len(results) == 1 and results[0]['id'] == previous['id'] == latest['id']
    assert results[0]['deadline'] == '2026-12-01'
    assert results[0]['vacancy_status'] == 'unverified'
    assert results[0]['archive_reason'] == ''


def test_archive_keeps_other_sources_and_respects_himalayas_expiry_rule(bd_clock):
    rows = [role(id='expired-himalayas', source='Himalayas', deadline='2026-11-21'),
            role(id='current-himalayas', source='Himalayas', deadline='2026-11-22'),
            role(id='expired-jobicy', source='Jobicy', deadline='2026-11-21')]
    result = c.annotate_freshness(rows)
    assert {job['id'] for job in result} == {'current-himalayas', 'expired-jobicy'}
    archived = next(job for job in result if job['id'] == 'expired-jobicy')
    assert archived['vacancy_status'] == 'expired' and archived['archive_reason'] == 'deadline_passed'
