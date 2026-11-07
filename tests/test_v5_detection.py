"""v5 detection engine: relevance, Bangla dates, ATS providers, alerts, feeds, dedup."""
from __future__ import annotations

import json

import pytest

from collector import ats, collect as c, custom_feeds, email_alerts, free_feeds, textmine
from collector.relevance import assess


@pytest.mark.parametrize('title', [
    'Network Security Engineer', 'Senior Officer, IS Audit', 'Firewall Administrator', 'IAM Engineer',
    'Security Manager (IT)', 'Head of Information Security', 'Associate, Information Security',
    'Engineer, Cyber Defense Operations', 'Senior InfoSec Engineer', 'Detection Engineer',
    'আইটি অডিট কর্মকর্তা', 'Cloud Security Architect', 'Data Protection Officer', 'Purple Team Lead'])
def test_relevant_titles(title):
    assert assess(title).relevant, title


@pytest.mark.parametrize('title', [
    'Mechanisms Engineer', 'Credit Audit Officer', 'Security Manager', 'ISO 9001 Auditor', 'Senior Officer',
    'AML Compliance Analyst', 'Social Security Officer', 'Food Security Analyst', 'Progress Engineer',
    'Security Supervisor', 'Sales Executive, Securities', 'Loss Prevention Officer'])
def test_irrelevant_titles(title):
    assert not assess(title).relevant, title


def test_generic_bank_title_with_security_department_description():
    r = assess('Senior Principal Officer', 'Place of posting: Information Security Division, Head Office. SIEM, ISO 27001.')
    assert r.relevant and r.score >= 50


def test_associate_is_not_categorised_as_soc():
    assert c.categorize('Associate, Information Security') != 'SOC & Threat Detection'
    assert c.categorize('SOC Analyst L2') == 'SOC & Threat Detection'


def test_bangla_and_english_deadlines_and_experience():
    assert textmine.find_deadline('আবেদনের শেষ তারিখ: ২০ নভেম্বর ২০২৬') == '2026-11-20'
    assert textmine.find_deadline('Application Deadline: 5th December, 2026') == '2026-12-05'
    assert textmine.find_deadline('Last date of application 30-11-2026') == '2026-11-30'
    assert textmine.parse_date('Nov 7, 2026') == '2026-11-07'
    assert textmine.years_required('At least three years of experience in SOC') == 3
    assert textmine.years_required('ন্যূনতম ৫ বছরের অভিজ্ঞতা') == 5
    job = c.new_job(title='Information Security Officer', company='X Bank', url='https://x.example/j/1',
                    source='Official employer', sources=[], description='Apply before 15 December 2026. Dhaka office.')
    assert job['deadline'] == '2026-12-15' and job['location'] == 'Dhaka, Bangladesh'
    assert job['relevance_score'] >= 70 and 'information security' in job['matched_terms']


def test_classify_region():
    assert c.classify_region('Dhaka, Bangladesh')['region'] == 'Bangladesh'
    intl = c.classify_region('Remote - Worldwide', remote=True)
    assert intl['region'] == 'International' and intl['eligibility_confidence'] == 'confirmed'
    assert c.classify_region('Remote - US only', remote=True) is None
    assert c.classify_region('London, UK') is None


def test_greenhouse_keeps_worldwide_remote_role_as_international():
    data = {'jobs': [{'title': 'Security Engineer', 'absolute_url': 'https://boards.greenhouse.io/x/jobs/1',
                      'location': {'name': 'Home based - Worldwide'}, 'content': 'Detection and response'}]}
    out = c.list_greenhouse(data, 'Canonical', [])
    assert len(out) == 1 and out[0]['region'] == 'International'


class Resp:
    def __init__(self, data=None, content=b'', status=200, text=''):
        self.data, self.content, self.status_code, self.text = data, content, status, text
        self.ok = status < 400

    def raise_for_status(self):
        if self.status_code >= 400:
            import requests
            raise requests.HTTPError(response=self)

    def json(self):
        return self.data


class Session:
    def __init__(self, routes):
        self.routes, self.calls = routes, []

    def _match(self, url):
        self.calls.append(url)
        for key, value in self.routes.items():
            if key in url:
                return value(url) if callable(value) else value
        raise AssertionError('unexpected ' + url)

    def get(self, url, **kw):
        return self._match(url)

    def post(self, url, **kw):
        return self._match(url)


def test_workable_smartrecruiters_workday_parsers():
    s = Session({
        'apply.workable.com/api/v1/widget/accounts/pathao': Resp({'jobs': [
            {'title': 'Information Security Engineer', 'url': 'https://apply.workable.com/pathao/j/AB12/',
             'locations': [{'city': 'Dhaka', 'country': 'Bangladesh'}], 'description': '<p>SIEM and VAPT</p>'},
            {'title': 'Accountant', 'url': 'https://apply.workable.com/pathao/j/CD34/', 'country': 'Bangladesh'}]}),
        'robots.txt': Resp(status=404),
        '/postings/77': Resp({'jobAd': {'sections': {'jobDescription': {'text': 'Run the SOC'}}}}),
        'smartrecruiters.com/v1/companies/Acme/postings': Resp({'totalFound': 1, 'content': [
            {'id': '77', 'name': 'SOC Analyst', 'location': {'city': 'Dhaka', 'country': 'bd', 'fullLocation': 'Dhaka, Bangladesh'}}]}),
        '/wday/cxs/hsbc/external/jobs': Resp({'jobPostings': [
            {'title': 'Cyber Security Analyst', 'externalPath': '/job/Dhaka/Cyber_R1', 'locationsText': 'Dhaka'}]}),
        '/wday/cxs/hsbc/external/job/Dhaka/Cyber_R1': Resp({'jobPostingInfo': {
            'jobDescription': 'Threat detection', 'location': 'Dhaka', 'country': {'descriptor': 'Bangladesh'}}}),
    })
    sources = []
    raw = ats.fetch_board(s, 'workable', 'pathao', c.UA, lambda t: True)
    jobs = [j for j in (c.ats_posting_to_job(r, company='Pathao', provider='workable', sources=sources) for r in raw) if j]
    assert [j['title'] for j in jobs] == ['Information Security Engineer']
    raw = ats.fetch_board(s, 'smartrecruiters', 'Acme', c.UA, lambda t: True)
    assert raw[0]['url'] == 'https://jobs.smartrecruiters.com/Acme/77' and 'SOC' in raw[0]['description']
    raw = ats.fetch_board(s, 'workday', 'hsbc|wd3|external', c.UA, lambda t: True)
    job = c.ats_posting_to_job(raw[0], company='HSBC', provider='workday', sources=sources)
    assert job and job['region'] == 'Bangladesh' and job['source'] == 'Workday career site'


def test_linkedin_and_bdjobs_alert_email_parsing():
    html = '''<table><tr><td><a href="https://www.linkedin.com/comm/jobs/view/4012345678/?trackingId=x">Information Security Officer</a>
      <p>Dutch-Bangla Bank PLC</p><p>Dhaka, Bangladesh</p></td></tr>
      <tr><td><a href="https://www.linkedin.com/comm/jobs/view/4012345678/?trk=img"><img src="x"></a></td></tr>
      <tr><td><a href="https://click.example/r?url=https%3A%2F%2Fjobs.bdjobs.com%2Fjobdetails.asp%3Fid%3D1312345">SOC Analyst (L1)</a>
      <div>Grameenphone Ltd.</div></td></tr>
      <tr><td><a href="https://www.linkedin.com/comm/jobs/view/4099999999/">Sales Manager</a><p>X</p></td></tr></table>'''
    rows = email_alerts.parse_alert_email(html)
    urls = {r['url']: r for r in rows}
    assert urls['https://www.linkedin.com/jobs/view/4012345678/']['company'] == 'Dutch-Bangla Bank PLC'
    assert 'https://jobs.bdjobs.com/jobdetails.asp?id=1312345' in urls
    jobs = email_alerts.rows_to_jobs(rows, [])
    assert {j['title'] for j in jobs} == {'Information Security Officer', 'SOC Analyst (L1)'}
    assert all(j['verification_level'] == 'Email alert (subscribed)' for j in jobs)


def test_google_alert_atom_feed():
    atom = b'''<feed xmlns="http://www.w3.org/2005/Atom"><entry><title type="html">City Bank hiring &lt;b&gt;Information Security&lt;/b&gt; Officer</title>
      <link href="https://www.google.com/url?rct=j&amp;sa=t&amp;url=https://www.thecitybank.com/careers/iso-1&amp;ct=ga"/>
      <content type="html">Job circular, Dhaka. Apply by 30 November 2026</content></entry>
      <entry><title>Bank opens new branch</title><link href="https://news.example/a"/><content>Branch</content></entry></feed>'''
    jobs = custom_feeds.parse_feed(atom, {'name': 'GA', 'region': 'auto'}, [])
    assert len(jobs) == 1 and jobs[0]['source_url'] == 'https://www.thecitybank.com/careers/iso-1'
    assert jobs[0]['deadline'] == '2026-11-30' and jobs[0]['region'] == 'Bangladesh'


def test_we_work_remotely_rss():
    rss = b'''<rss><channel><item><title>Acme: Senior Application Security Engineer</title><region>Anywhere in the World</region>
      <link>https://weworkremotely.com/remote-jobs/acme-appsec</link><description>OWASP, threat modelling</description></item>
      <item><title>Beta: Security Engineer</title><region>USA Only</region><link>https://weworkremotely.com/remote-jobs/b</link></item></channel></rss>'''
    jobs = free_feeds.parse_wwr(rss, [])
    assert len(jobs) == 1 and jobs[0]['company'] == 'Acme' and jobs[0]['region'] == 'International'


def test_microdata_jobposting_is_read():
    html = '''<div itemscope itemtype="https://schema.org/JobPosting"><h1 itemprop="title">Cyber Security Analyst</h1>
      <div itemprop="description">Monitor SIEM alerts for the bank.</div><meta itemprop="datePosted" content="2026-11-01">
      <div itemprop="jobLocation" itemscope itemtype="https://schema.org/Place"><span itemprop="address">Dhaka, Bangladesh</span></div></div>'''
    jobs = c.scrape_official_job(html, 'https://bank.example/careers/1', [], 'Demo Bank')
    assert len(jobs) == 1 and jobs[0]['posted_at'] == '2026-11-01'


def test_cross_source_fold_keeps_alternate_link():
    off = c.new_job(title='Information Security Officer', company='City Bank PLC', url='https://bank.example/careers/1',
                    source='Official employer', sources=[], verification_level='Official page parsed')
    alert = c.new_job(title='Information Security Officer', company='City Bank Limited',
                      url='https://www.linkedin.com/jobs/view/1/', source='LinkedIn alert email', sources=[],
                      verification_level='Email alert (subscribed)', deadline='2026-12-01')
    merged = c.deduplicate([off, alert])
    assert len(merged) == 1 and merged[0]['source_url'] == off['source_url']
    assert merged[0]['also_listed_on'][0]['url'].startswith('https://www.linkedin.com')


def test_parallel_coverage_round_keeps_order_and_counts_every_source():
    srcs = [{'name': f'Bank {i}', 'id': f'b{i}', 'sector': 'Banking', 'mode': 'career',
             'website': f'https://b{i}.example', 'careers_url': f'https://b{i}.example/careers'} for i in range(8)]

    class Stub:
        failures, discovered_ats, ats_redirects = {}, [], {}

        def fetch(self, url, **kw):
            if url.endswith('/careers'):
                return '<html><title>Careers</title><a href="https://apply.workable.com/acme/">Jobs</a></html>'
            return None
    calls = []
    jobs, health = c.coverage_round(srcs, Stub(), 8, detail_budget=0, on_source=lambda o, j: calls.append(o['name']),
                                    workers=4)
    assert [h['name'] for h in health] == [s['name'] for s in sorted(srcs, key=lambda x: x['name'])]
    assert len(calls) == 8


def test_discovery_finds_embeds_and_rejects_lookalikes():
    html = '''<iframe src="https://boards.greenhouse.io/embed/job_board?for=bkash"></iframe>
       <a href="https://bkash.wd3.myworkdayjobs.com/en-US/careers/job/1">x</a>
       <a href="https://jobs.lever.co.evil.example/steal">e</a><a href="https://apply.workable.com/widget/x">w</a>'''
    found = {(b['provider'], b['board_token']) for b in c.discover_ats_links(html, 'https://bkash.com/careers', 'bKash')}
    assert found == {('greenhouse', 'bkash'), ('workday', 'bkash|wd3|careers')}


def test_brave_search_skipped_without_key(monkeypatch):
    from collector import search_apis
    monkeypatch.delenv('BRAVE_API_KEY', raising=False)
    assert search_apis.brave_search(None, {}, [])[0:2] == ([], [])
