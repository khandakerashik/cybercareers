"""Deterministic regressions for alert loss, pagination and false attribution."""
import email
import email.policy

import pytest
import requests

from collector import email_alerts as alerts, search_apis as apis, custom_feeds


class Response:
    def __init__(self, payload=None, status=200, content=b''):
        self.payload = payload
        self.status_code = status
        self.headers = {}
        self.content = content

    def raise_for_status(self):
        if self.status_code >= 400:
            raise requests.HTTPError(response=self)

    def json(self):
        return self.payload


class Session:
    def __init__(self, responses):
        self.responses = iter(responses)
        self.calls = []

    def get(self, url, **kwargs):
        self.calls.append((url, kwargs))
        return next(self.responses)

    post = get


def index_job(i):
    return {'title': 'Acme hiring SOC Analyst in Dhaka, Bangladesh | LinkedIn',
            'url': f'https://bd.linkedin.com/jobs/view/soc-analyst-{i}/',
            'description': 'Hiring for our Dhaka team. Responsibilities: SIEM monitoring. Apply now.'}


def test_canonical_portal_ids_and_domain_spoofing():
    assert alerts.canonical_portal_job('https://bd.linkedin.com/comm/jobs/view/soc-12345678/?trackingId=x') == ('LinkedIn', 'https://www.linkedin.com/jobs/view/12345678/')
    assert alerts.canonical_portal_job('https://www.linkedin.com/jobs/search/?currentJobId=12345678') == ('LinkedIn', 'https://www.linkedin.com/jobs/view/12345678/')
    assert alerts.canonical_portal_job('https://click.example/?url=https%253A%252F%252Fbd.linkedin.com%252Fjobs%252Fview%252F12345678%252F')[1].endswith('/12345678/')
    assert alerts.canonical_portal_job('https://jobs.bdjobs.com/jobdetails.asp?ID=12345&ln=1')[1].endswith('id=12345')
    for url in ('https://evil-linkedin.com/jobs/view/12345678/', 'https://linkedin.com.attacker.test/jobs/view/12345678/',
                'https://www.linkedin.com/jobs/search/?keywords=SOC', 'https://user:pw@www.linkedin.com/jobs/view/12345678/'):
        assert alerts.canonical_portal_job(url) is None


def test_nested_cards_preserve_company_and_do_not_mix_locations():
    html = '''<table><tr><td><div><a href="https://www.linkedin.com/comm/jobs/view/12345678/">SOC Analyst</a></div>
      <div>Dhaka Bank PLC</div><div>Dhaka, Bangladesh (Hybrid)</div></td></tr>
      <tr><td><div><a href="https://www.linkedin.com/jobs/view/87654321/">Cloud Security Engineer</a></div>
      <div>Foreign Corp</div><div>Toronto, Canada</div></td></tr></table>'''
    rows = alerts.parse_alert_email(html, received='2026-11-01')
    assert rows[0]['company'] == 'Dhaka Bank PLC'
    assert rows[0]['location'] == 'Dhaka, Bangladesh (Hybrid)'
    assert rows[1]['location'] == 'Toronto, Canada'
    jobs = alerts.rows_to_jobs(rows, [])
    assert len(jobs) == 1
    assert jobs[0]['posted_at'] == ''
    assert jobs[0]['alert_received_at'] == '2026-11-01'
    assert jobs[0]['last_seen_at'] == '2026-11-01'


def test_plain_text_alerts_recover_title_and_location():
    msg = email.message_from_string('''From: jobs-noreply@linkedin.com
Content-Type: text/plain; charset=utf-8

SOC Analyst
Acme Bank
Dhaka, Bangladesh
<https://www.linkedin.com/jobs/view/12345678/?a=1&b=2>

Application Security Engineer
Example Ltd
Remote - Worldwide
https://www.linkedin.com/comm/jobs/view/87654321/
''', policy=email.policy.default)
    rows = alerts.parse_alert_email(alerts._html_of(msg), received='2026-11-01')
    assert [r['title'] for r in rows] == ['SOC Analyst', 'Application Security Engineer']
    jobs = alerts.rows_to_jobs(rows, [])
    assert {x['region'] for x in jobs} == {'Bangladesh', 'International'}


def test_repeated_apply_link_and_event_are_not_new_jobs():
    html = '''<div><a href="https://linkedin.com/jobs/view/12345678/">SOC Analyst</a><p>Acme Bank</p><p>Dhaka, Bangladesh</p>
      <a href="https://bd.linkedin.com/comm/jobs/view/12345678/">Apply now</a></div>
      <div><a href="https://www.linkedin.com/jobs/view/23456789/">Cyber Security Conference</a><p>Acme</p><p>Dhaka</p></div>'''
    jobs = alerts.rows_to_jobs(alerts.parse_alert_email(html), [])
    assert len(jobs) == 1 and jobs[0]['title'] == 'SOC Analyst'


def test_missing_location_is_counted_without_guessing_bangladesh():
    stats = {}
    jobs = alerts.rows_to_jobs([{'title': 'SOC Analyst', 'platform': 'LinkedIn', 'url': 'https://www.linkedin.com/jobs/view/12345678/'}], [], diagnostics=stats)
    assert jobs == [] and stats['unresolved_location'] == 1


def test_imap_backlog_moves_past_newest_message_cap(monkeypatch):
    monkeypatch.setenv('ALERT_IMAP_USER', 'owner@example.test')
    monkeypatch.setenv('ALERT_IMAP_PASSWORD', 'secret')
    fetched = []
    msg = b'From: jobs-noreply@linkedin.com\nDate: Sun, 22 Nov 2026 10:00:00 +0000\nContent-Type: text/plain\n\nSOC Analyst\nAcme Bank\nDhaka, Bangladesh\nhttps://linkedin.com/jobs/view/12345678/\n'

    class Box:
        def __enter__(self): return self
        def __exit__(self, *args): pass
        def login(self, *args): pass
        def select(self, *args, **kwargs):
            assert kwargs['readonly'] is True
            return 'OK', [b'3']
        def response(self, name): return name, [b'500']
        def uid(self, command, *args):
            if command == 'search': return 'OK', [b'1 2 3']
            assert args[1] == '(BODY.PEEK[])'
            fetched.append(args[0])
            return 'OK', [(b'1', msg)]

    monkeypatch.setattr(alerts.imaplib, 'IMAP4_SSL', lambda *args, **kwargs: Box())
    state, stats = {}, {}
    alerts.fetch_alert_rows(2, state=state, diagnostics=stats)
    assert stats['remaining_messages'] == 1 and fetched == [b'3', b'1']
    alerts.fetch_alert_rows(2, state=state, diagnostics=stats)
    assert stats['remaining_messages'] == 0 and fetched == [b'3', b'1', b'2']
    alerts.fetch_alert_rows(2, state=state, diagnostics=stats)
    assert stats['messages_read'] == 0


def test_brave_pages_and_duplicate_results(monkeypatch):
    monkeypatch.setenv('BRAVE_API_KEY', 'key')
    monkeypatch.setenv('BRAVE_MAX_REQUESTS_PER_RUN', '4')
    monkeypatch.setattr(apis.time, 'sleep', lambda x: None)
    s = Session([Response({'query': {'more_results_available': True}, 'web': {'results': [index_job(12345678)]}}),
                 Response({'query': {'more_results_available': False}, 'web': {'results': [index_job(12345678), index_job(87654321)]}})])
    jobs, health, state = apis.brave_search(s, {}, [], per_run=1)
    assert len(jobs) == 2
    assert [c[1]['params']['offset'] for c in s.calls] == [0, 1]
    assert 'freshness' not in s.calls[0][1]['params']
    assert health[0]['requests_used'] == 2 and state['brave']['monthly_requests'] == 2


def test_brave_failure_does_not_abort_next_query(monkeypatch):
    monkeypatch.setenv('BRAVE_API_KEY', 'key')
    monkeypatch.setattr(apis.time, 'sleep', lambda x: None)
    s = Session([Response(status=500), Response({'query': {'more_results_available': False}, 'web': {'results': [index_job(12345678)]}})])
    jobs, health, state = apis.brave_search(s, {}, [], per_run=2)
    assert len(jobs) == 1 and len(s.calls) == 2
    assert health[0]['state'] == 'partial'


def test_brave_budget_persists_and_does_not_silently_spend(monkeypatch):
    monkeypatch.setenv('BRAVE_API_KEY', 'key')
    monkeypatch.setenv('BRAVE_MONTHLY_REQUEST_LIMIT', '1')
    s = Session([Response({'query': {'more_results_available': True}, 'web': {'results': [index_job(12345678)]}})])
    _, _, state = apis.brave_search(s, {}, [], per_run=2)
    assert state['brave']['page_cursors']
    _, health, _ = apis.brave_search(s, state, [], per_run=2)
    assert len(s.calls) == 1 and health[0]['state'] == 'cached'


def test_brave_resumes_saved_page(monkeypatch):
    monkeypatch.setenv('BRAVE_API_KEY', 'key')
    s = Session([Response({'query': {'more_results_available': False}, 'web': {'results': [index_job(12345678)]}})])
    apis.brave_search(s, {'brave': {'page_cursors': {apis.BRAVE_QUERIES[0]: 1}}}, [], per_run=1)
    assert s.calls[0][1]['params']['offset'] == 1


def test_jooble_requires_regional_endpoint_and_rejects_credential_exfiltration(monkeypatch):
    monkeypatch.setenv('JOOBLE_API_KEY', 'secret')
    for host in ('', 'jooble.org.attacker.test', 'https://jooble.org', 'user@jooble.org'):
        monkeypatch.setenv('JOOBLE_API_HOST', host)
        s = Session([])
        jobs, health, _ = apis.jooble_search(s, {}, [])
        assert not jobs and not s.calls and health[0]['reason'] == 'configuration'


def test_jooble_pagination_rejects_foreign_location(monkeypatch):
    monkeypatch.setenv('JOOBLE_API_KEY', 'key')
    monkeypatch.setenv('JOOBLE_API_HOST', 'jooble.org')
    def row(i, loc):
        return {'id': i, 'title': 'Security Engineer', 'location': loc, 'snippet': 'Develop application security controls.',
                'link': f'https://jooble.org/jdp/{i}', 'company': 'Acme', 'updated': '2026-11-20T00:00:00Z'}
    s = Session([Response({'totalCount': 3, 'jobs': [row(1, 'Toronto, Canada'), row(2, 'Dhaka, Bangladesh')]}),
                 Response({'totalCount': 3, 'jobs': [row(3, 'Dhaka, Bangladesh')]})])
    jobs, health, _ = apis.jooble_search(s, {}, [], per_run=1)
    assert len(jobs) == 2
    assert [call[1]['json']['page'] for call in s.calls] == [1, 2]
    assert all(call[1]['allow_redirects'] is False for call in s.calls)
    assert all(j['posted_at'] == '' and j['source_updated_at'] for j in jobs)


def test_custom_feed_rejects_event_and_malformed_success():
    body = b'''<rss><channel><item><title>SOC Analyst Workshop</title><description>Dhaka, apply now to attend the conference. Job advice.</description><link>https://example.com/events/soc</link></item></channel></rss>'''
    assert custom_feeds.parse_feed(body, {'region': 'bangladesh'}, []) == []
    stats = {}
    assert custom_feeds.parse_feed('<html>Access denied</html>', {}, [], diagnostics=stats) == []
    assert stats['invalid_payload']
    s = Session([Response(content=b'<html>Challenge</html>')])
    _, health, _ = custom_feeds.collect_custom_feeds(s, [{'url': 'https://example.com/rss'}], {}, [], clock=1)
    assert health[0]['state'] == 'error'


def test_custom_feed_region_filter_does_not_override_foreign_location():
    body = b'''<rss><channel><item><title>Hiring Information Security Officer</title><location>Toronto, Canada</location>
      <description>Responsibilities: security testing. Requirements: CISSP. Apply now.</description><link>https://example.com/jobs/security-1</link></item></channel></rss>'''
    assert custom_feeds.parse_feed(body, {'region': 'bangladesh'}, []) == []


def test_mailbox_checkpoint_is_not_committed_when_conversion_fails(monkeypatch):
    monkeypatch.setenv('ALERT_IMAP_USER', 'owner@example.test')
    monkeypatch.setenv('ALERT_IMAP_PASSWORD', 'secret')
    previous = {'scope': 'mailbox', 'processed_uids': ['10']}
    state = {'alert_mailbox': previous.copy()}
    def fetch(*, state, diagnostics):
        state['alert_mailbox'] = {'scope': 'mailbox', 'processed_uids': ['10', '11']}
        diagnostics.update(messages_read=1, remaining_messages=0, messages_failed=0)
        return []
    monkeypatch.setattr(alerts, 'fetch_alert_rows', fetch)
    monkeypatch.setattr(alerts, 'rows_to_jobs', lambda *a, **kw: (_ for _ in ()).throw(ValueError('conversion failed')))
    jobs, outcomes = alerts.collect_email_alerts([], state=state)
    assert jobs == [] and outcomes[0]['state'] == 'error'
    assert state['alert_mailbox'] == previous


def test_mailbox_checkpoint_commits_after_success(monkeypatch):
    monkeypatch.setenv('ALERT_IMAP_USER', 'owner@example.test')
    monkeypatch.setenv('ALERT_IMAP_PASSWORD', 'secret')
    state = {}
    def fetch(*, state, diagnostics):
        state['alert_mailbox'] = {'scope': 'mailbox', 'processed_uids': ['11']}
        diagnostics.update(messages_read=1, remaining_messages=0, messages_failed=0)
        return []
    monkeypatch.setattr(alerts, 'fetch_alert_rows', fetch)
    jobs, outcomes = alerts.collect_email_alerts([], state=state)
    assert outcomes[0]['state'] == 'ok' and state['alert_mailbox']['processed_uids'] == ['11']


def test_latest_email_wins_over_backlog_copy():
    common = {'title': 'SOC Analyst', 'platform': 'LinkedIn', 'url': 'https://www.linkedin.com/jobs/view/12345678/',
              'company': 'Acme Bank', 'location': 'Dhaka, Bangladesh'}
    # Fresh-reserve selection emits newest first, followed by older backlog.
    jobs = alerts.rows_to_jobs([{**common, 'received': '2026-11-22'}, {**common, 'received': '2026-11-01'}], [])
    assert len(jobs) == 1
    assert jobs[0]['alert_received_at'] == jobs[0]['last_seen_at'] == jobs[0]['last_observed_at'] == '2026-11-22'


def test_single_message_budget_alternates_freshness_and_backlog(monkeypatch):
    monkeypatch.setenv('ALERT_IMAP_USER', 'owner@example.test')
    monkeypatch.setenv('ALERT_IMAP_PASSWORD', 'secret')
    fetched = []
    class Box:
        def __enter__(self): return self
        def __exit__(self, *args): pass
        def login(self, *args): pass
        def select(self, *args, **kwargs): return 'OK', [b'10']
        def response(self, name): return name, [b'500']
        def uid(self, command, *args):
            if command == 'search': return 'OK', [b'1 2 3 4 5 6 7 8 9 10']
            fetched.append(args[0])
            return 'OK', [(b'1', b'From: jobs-noreply@linkedin.com\nContent-Type: text/plain\n\nNo postings')]
    monkeypatch.setattr(alerts.imaplib, 'IMAP4_SSL', lambda *args, **kwargs: Box())
    state = {}
    alerts.fetch_alert_rows(1, state=state)
    alerts.fetch_alert_rows(1, state=state)
    alerts.fetch_alert_rows(1, state=state)
    assert fetched == [b'10', b'1', b'9']


def test_brave_does_not_forward_api_key_through_redirect(monkeypatch):
    monkeypatch.setenv('BRAVE_API_KEY', 'private-api-token')
    response = Response(status=302)
    response.headers['Location'] = 'https://other.example/search'
    session = Session([response])
    jobs, outcomes, _ = apis.brave_search(session, {}, [], per_run=1)
    assert not jobs and outcomes[0]['state'] == 'error'
    assert session.calls[0][1]['allow_redirects'] is False
    assert 'private-api-token' not in str(outcomes)


def test_root_merges_canonical_linkedin_alias_but_keeps_distinct_ids():
    from collector import collect as c
    first = c.new_job(title='SOC Analyst', company='Acme Bank', url='https://bd.linkedin.com/jobs/view/soc-12345678/?trk=x',
                      source='LinkedIn index', sources=[], location='Dhaka, Bangladesh', verification_level='Search indexed (unverified)')
    same = c.new_job(title='SOC Analyst', company='Acme Bank', url='https://linkedin.com/comm/jobs/view/12345678/',
                     source='LinkedIn alert email', sources=[], location='Dhaka, Bangladesh', verification_level='Email alert (subscribed)')
    other = c.new_job(title='SOC Analyst', company='Acme Bank', url='https://linkedin.com/jobs/view/87654321/',
                      source='LinkedIn alert email', sources=[], location='Dhaka, Bangladesh', verification_level='Email alert (subscribed)')
    official = c.new_job(title='SOC Analyst', company='Acme Bank', url='https://acme.example/jobs/one', source='Official employer',
                         sources=[], location='Dhaka, Bangladesh', verification_level='Official page parsed')
    assert len(c.deduplicate([first, same])) == 1
    assert len(c.deduplicate([first, same, other, official])) == 3


def test_root_preserves_generic_requisition_reference_parameter():
    from collector import collect as c
    assert c.canonical_job_url('https://acme.example/vacancy?ref=REQ1') != c.canonical_job_url('https://acme.example/vacancy?ref=REQ2')


def test_root_rejects_malformed_port_without_crashing_dedup():
    from collector import collect as c
    assert not c.valid_url('https://example.com:bad/jobs/security')
    assert c.canonical_job_url('https://example.com:bad/jobs/security') == ''


def test_root_preserves_provider_update_metadata_from_a_duplicate():
    from collector import collect as c
    low = c.new_job(title='SOC Analyst', company='Acme', url='https://acme.example/jobs/1', source='Jooble API',
                    sources=[], verification_level='Aggregator API', source_updated_at='2026-11-22T00:00:00Z')
    high = c.new_job(title='SOC Analyst', company='Acme', url='https://acme.example/jobs/1', source='Official employer',
                     sources=[], verification_level='Official page parsed')
    result = c.deduplicate([low, high])
    assert len(result) == 1 and result[0]['source_updated_at'] == '2026-11-22T00:00:00Z'


def test_old_alert_cannot_expire_a_current_official_vacancy():
    from datetime import timedelta
    from collector import collect as c
    past = (c.now_bd().date() - timedelta(days=30)).isoformat()
    current = c.new_job(title='SOC Analyst', company='Acme', url='https://acme.example/jobs/current', source='Official employer',
                        sources=[], verification_level='Official page parsed', location='Dhaka, Bangladesh')
    old = c.new_job(title='SOC Analyst', company='Acme', url='https://linkedin.com/jobs/view/12345678/', source='LinkedIn alert email',
                    sources=[], verification_level='Email alert (subscribed)', deadline=past, alert_received_at=past,
                    location='Dhaka, Bangladesh')
    old['last_seen_at'] = past
    results = c.annotate_freshness(c.deduplicate([current, old]))
    official = next(job for job in results if job['source_url'] == current['source_url'])
    assert official['vacancy_status'] != 'expired'
    assert official['deadline'] != past


def test_same_posting_official_deadline_extension_uses_new_observation():
    from datetime import timedelta
    from collector import collect as c
    today = c.now_bd().date()
    base = {'title': 'SOC Analyst', 'company': 'Acme', 'url': 'https://acme.example/jobs/soc-1',
            'source': 'Official employer', 'sources': [], 'verification_level': 'Official page parsed'}
    previous = c.new_job(**base, description='A detailed earlier description. ' * 30,
                         deadline=(today - timedelta(days=1)).isoformat())
    previous['last_seen_at'] = (today - timedelta(days=2)).isoformat()
    previous['last_observed_at'] = previous['last_seen_at'] + 'T00:00:00+06:00'
    latest = c.new_job(**base, description='Updated vacancy. The application deadline has been extended.',
                       deadline=(today + timedelta(days=14)).isoformat())
    results = c.deduplicate([previous, latest])
    assert len(results) == 1
    assert results[0]['deadline'] == latest['deadline']


def test_jooble_clamped_page_sizes_use_observed_count(monkeypatch):
    monkeypatch.setenv('JOOBLE_API_KEY', 'key')
    monkeypatch.setenv('JOOBLE_API_HOST', 'jooble.org')
    monkeypatch.setenv('JOOBLE_PAGES_PER_QUERY', '4')
    def rows(start, count):
        return [{'id': i, 'title': 'SOC Analyst', 'location': 'Dhaka, Bangladesh',
                 'company': 'Acme', 'link': f'https://jooble.org/jdp/{i}'} for i in range(start, start+count)]
    session = Session([Response({'totalCount': 75, 'jobs': rows(1, 20)}),
                       Response({'totalCount': 75, 'jobs': rows(21, 20)}),
                       Response({'totalCount': 75, 'jobs': rows(41, 20)}),
                       Response({'totalCount': 75, 'jobs': rows(61, 15)})])
    jobs, outcomes, _ = apis.jooble_search(session, {}, [], per_run=1)
    assert len(jobs) == 75
    assert [call[1]['json']['page'] for call in session.calls] == [1, 2, 3, 4]
    assert outcomes[0]['truncated_queries'] == 0


def test_repeated_provider_pages_are_marked_limited(monkeypatch):
    monkeypatch.setenv('JOOBLE_API_KEY', 'key')
    monkeypatch.setenv('JOOBLE_API_HOST', 'jooble.org')
    row = {'id': 1, 'title': 'SOC Analyst', 'location': 'Dhaka, Bangladesh', 'company': 'Acme', 'link': 'https://jooble.org/jdp/1'}
    session = Session([Response({'totalCount': 5, 'jobs': [row]}), Response({'totalCount': 5, 'jobs': [row]})])
    jobs, outcomes, _ = apis.jooble_search(session, {}, [], per_run=1)
    assert len(jobs) == 1 and len(session.calls) == 2
    assert outcomes[0]['coverage_limited'] and outcomes[0]['truncated_queries'] == 1


def test_brave_short_page_without_end_signal_does_not_mean_exhausted(monkeypatch):
    monkeypatch.setenv('BRAVE_API_KEY', 'key')
    monkeypatch.setattr(apis.time, 'sleep', lambda value: None)
    session = Session([Response({'web': {'results': [index_job(12345678)]}}),
                       Response({'query': {'more_results_available': False}, 'web': {'results': [index_job(87654321)]}})])
    jobs, outcomes, _ = apis.brave_search(session, {}, [], per_run=1)
    assert len(jobs) == 2
    assert len(session.calls) == 2 and outcomes[0]['queries_completed'] == 1
