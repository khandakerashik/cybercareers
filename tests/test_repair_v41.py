"""Tests for broken website/career URLs, redirect policies and fallback outcomes."""
import json
from pathlib import Path
from urllib.parse import urlparse
from collector import collect as c
from collector.telemetry import CollectionTelemetry


class FakeResponse:
    def __init__(self, status=200, body='', location='', content_type='text/html'):
        self.status_code = status
        self.text = body
        self.content = body.encode()
        self.headers = {'Content-Type': content_type}
        if location:
            self.headers['Location'] = location
        self.ok = 200 <= status < 300


class FakeSession:
    def __init__(self, responses):
        self.headers = {}
        self.responses = responses
        self.urls = []
    def get(self, url, **kwargs):
        self.urls.append(url)
        result = self.responses.get(url)
        if isinstance(result, Exception):
            raise result
        if result is None:
            raise AssertionError('Unexpected URL: ' + url)
        return result


def example_source(**kwargs):
    return dict(name='Example Bank', id='bank-1', sector='Banking',
                website='https://bank.example', careers_url='https://bank.example/career',
                mode='career', **kwargs)


def test_robots_redirect_to_canonical_www_is_accepted():
    fs=FakeSession({
      'https://bank.example/robots.txt': FakeResponse(301, location='https://www.bank.example/robots.txt'),
      'https://www.bank.example/robots.txt':FakeResponse(200,'User-agent: *\nDisallow: /private\nAllow: /',content_type='text/plain'),
      'https://bank.example/career':FakeResponse(200,'<html><title>Careers</title><body>Open jobs</body></html>'),
    })
    fetch=c.CompliantFetcher([example_source()], fs)
    assert fetch.fetch('https://bank.example/career')
    assert fs.urls[:2]==['https://bank.example/robots.txt', 'https://www.bank.example/robots.txt']
    assert not fetch.robots_allow('https://bank.example/private')


def test_robots_server_error_remains_a_real_failure():
    fs=FakeSession({'https://bank.example/robots.txt': FakeResponse(503)})
    fetch=c.CompliantFetcher([example_source()],fs)
    assert fetch.fetch('https://bank.example/career') is None
    assert 'robots.txt HTTP 503' in fetch.failures['https://bank.example/career']
    assert len(fs.urls)==1


def test_robots_4xx_means_no_restrictions_per_rfc9309():
    fs=FakeSession({'https://bank.example/robots.txt': FakeResponse(403),
                    'https://bank.example/career':FakeResponse(200,'<html><title>Careers</title></html>')})
    assert c.CompliantFetcher([example_source()],fs).fetch('https://bank.example/career')


def test_robots_longest_match_allows_careers_under_global_disallow():
    from collector.robots import RobotsPolicy
    p=RobotsPolicy('User-agent: *\nDisallow: /\nAllow: /careers/\nDisallow: /careers/*.pdf$\n\nUser-agent: BadBot\nDisallow: /')
    assert p.can_fetch(c.UA,'https://x.example/careers/security-officer')
    assert not p.can_fetch(c.UA,'https://x.example/about')
    assert not p.can_fetch(c.UA,'https://x.example/careers/circular.pdf')
    assert p.can_fetch(c.UA,'https://x.example/careers/circular.pdf?v=1')
    named=RobotsPolicy('User-agent: CyberCareersBD\nDisallow: /jobs\n\nUser-agent: *\nAllow: /')
    assert not named.can_fetch(c.UA,'https://x.example/jobs/1')


def test_career_redirect_to_public_ats_is_captured_not_failed_silently():
    fs=FakeSession({'https://bank.example/robots.txt':FakeResponse(404),
                    'https://bank.example/career':FakeResponse(302,location='https://apply.workable.com/examplebank/')})
    fetch=c.CompliantFetcher([example_source()],fs)
    assert fetch.fetch('https://bank.example/career') is None
    assert fetch.ats_redirects['https://bank.example/career']=='https://apply.workable.com/examplebank/'


def test_official_page_redirect_to_apex_host_works():
    fs=FakeSession({
      'https://bank.example/robots.txt':FakeResponse(404),
      'https://www.bank.example/robots.txt':FakeResponse(404),
      'https://bank.example/career':FakeResponse(301,location='https://www.bank.example/career'),
      'https://www.bank.example/career':FakeResponse(200,'<html><title>Bank Careers</title></html>')
    })
    assert c.CompliantFetcher([example_source()],fs).fetch('https://bank.example/career')


def test_page_redirect_to_unapproved_domain_stays_blocked():
    fs=FakeSession({'https://bank.example/robots.txt':FakeResponse(404),
                    'https://bank.example/career':FakeResponse(302,location='https://example.net/career')})
    fetch=c.CompliantFetcher([example_source()],fs)
    assert fetch.fetch('https://bank.example/career') is None
    assert 'outside approved employer hosts' in fetch.failures['https://bank.example/career']


def test_backup_verified_career_page_recovers_failed_primary(monkeypatch):
    src=example_source(career_alternates=['https://careers.bank.example/jobs'])
    class StubFetcher:
        failures = {}
        discovered_ats=[]
        def fetch(self,url,**kwargs):
            if url==src['careers_url']:
                self.failures[url]='HTTP 404'
                return None
            if url=='https://careers.bank.example/jobs':
                return '<html><head><title>Bank jobs</title></head><body>No new roles</body></html>'
            raise AssertionError(url)
    assert c.CompliantFetcher([src]).is_official_allowed('https://careers.bank.example/jobs')
    res,health=c.coverage_round([src],StubFetcher(),1,detail_budget=0)
    assert health[0]['state']=='ok'
    assert health[0]['jobs_found']==0
    assert 'fallback used' in health[0]['message']
    assert health[0]['checked_urls']==2


def test_homepage_without_career_link_is_limited_not_success(monkeypatch):
    src={'name':'Demo Employer','id':'bank-2','sector':'Banking','website':'https://demo.example','careers_url':'','mode':'search'}
    class StubFetcher:
        failures={}
        discovered_ats=[]
        def fetch(self,url,**kwargs):
            if url==src['website']:
                return '<html><title>Company Home</title><p>Welcome to our website</p></html>'
            return None
    monkeypatch.setattr(c,'sitemap_candidates',lambda *args,**kwargs:[])
    _,health=c.coverage_round([src],StubFetcher(),1,detail_budget=0)
    assert health[0]['state']=='partial'
    assert 'not verified' in health[0]['message']


def test_homepage_with_career_link_is_success(monkeypatch):
    src={'name':'Demo Employer','id':'bank-2','sector':'Banking','website':'https://demo.example','careers_url':'','mode':'search'}
    class StubFetcher:
        failures={}
        discovered_ats=[]
        def fetch(self,url,**kwargs):
            if url==src['website']:
                return '<html><title>Home</title><a href="/careers">Careers</a></html>'
            if url=='https://demo.example/careers':
                return '<html><title>Career</title><p>No positions today</p></html>'
            return None
    monkeypatch.setattr(c,'sitemap_candidates',lambda *args,**kwargs:[])
    _,health=c.coverage_round([src],StubFetcher(),1,detail_budget=2)
    assert health[0]['state']=='ok'


def test_source_health_has_amber_partial_and_preserves_ten_history(tmp_path):
    t=CollectionTelemetry(tmp_path,total=3)
    for status in ('failed','partial','ok'):
        t.completed(source_id='example',name='Example Bank',sector='Banking',mode='Official employer',state=status)
    obj=json.loads((tmp_path/'source_health.json').read_text())
    h=obj['sources']['example']
    assert [x['result'] for x in h['history']]==['failed','partial','success']
    assert t.progress['partial']==1 and t.progress['failed']==1 and t.progress['succeeded']==1


def test_reviewed_employer_urls_replaced_outdated_homepages():
    a={s['name']:s for s in c.get_json(c.DATA/'sources.json',[])}
    assert a['Akij Group']['careers_url'].startswith('https://career.akijgroup.co/')
    assert a['Al-Arafah Islami Bank']['careers_url'].startswith('https://www.aibl.com.bd/')
    assert 'Career' in a['NCC Bank']['careers_url']
    assert 'recruitment.php' in a['Rajshahi Krishi Unnayan Bank']['careers_url']
    assert 'career-job-openings' in a['Padma Bank']['careers_url']
    assert 'career/' in a['Premier Bank']['careers_url']
    assert a['South Bangla Agriculture & Commerce Bank']['mode']=='restricted'
    assert a['Square Group']['careers_url'].startswith('https://career.squarepharma.com.bd/')
