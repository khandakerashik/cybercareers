"""Regression tests for measured source failures and missed later-page roles."""
import json
import threading
from concurrent.futures import ThreadPoolExecutor

import pytest

from collector import ats, collect as c, render


SOURCE = {'id': 'bank-52', 'name': 'Example Bank', 'sector': 'Banking', 'mode': 'career',
          'website': 'https://bank.example', 'careers_url': 'https://bank.example/careers'}


class Response:
    def __init__(self, body='', status=200, headers=None, data=None):
        self.status_code=status
        self.text=body
        self.content=body.encode()
        self.headers={'Content-Type':'text/html', **(headers or {})}
        self.ok=200<=status<300
        self.data=data

    def raise_for_status(self):
        if not self.ok:raise ValueError(self.status_code)

    def json(self):return self.data


class Session:
    def __init__(self, responses):
        self.headers={}
        self.responses=responses
        self.urls=[]

    def get(self,url,**kwargs):
        self.urls.append(url)
        return self.responses[url]


class Fetcher:
    def __init__(self,pages):
        self.pages=pages
        self.failures={}
        self.discovered_ats=[]
        self.ats_redirects={}
        self.resolved_urls={}
        self.urls=[]

    def fetch(self,url,**kwargs):
        self.urls.append(url)
        if url not in self.pages:self.failures[url]='HTTP 404'
        return self.pages.get(url)

    def is_official_allowed(self,url):return url.startswith('https://bank.example/')


def posting(title='Information Security Analyst'):
    return '<script type="application/ld+json">'+json.dumps({
        '@type':'JobPosting','title':title,'description':'Monitor SIEM alerts and investigate incidents.',
        'hiringOrganization':{'name':'Example Bank'},'jobLocation':{'address':'Dhaka, Bangladesh'},
    })+'</script>'


def test_canonical_redirect_is_used_to_resolve_relative_job_links(monkeypatch):
    monkeypatch.setattr(c,'MIN_HOST_DELAY',0)
    s=Session({'https://bank.example/robots.txt':Response(status=404),
        SOURCE['careers_url']:Response(status=301,headers={'Location':'/en/openings/'}),
        'https://bank.example/en/openings/':Response('<h1>Careers</h1><a href="security-analyst">Information Security Analyst</a>'),
        'https://bank.example/en/openings/security-analyst':Response(posting())})
    f=c.CompliantFetcher([SOURCE],s)
    outcome,jobs=c._check_employer(SOURCE,[SOURCE],f,c._Budget(4))
    assert f.resolved_urls[SOURCE['careers_url']]=='https://bank.example/en/openings/'
    assert 'https://bank.example/en/openings/security-analyst' in s.urls
    assert jobs and outcome['resolved_url']=='https://bank.example/en/openings/'


def test_soft_404_is_not_a_successful_source(monkeypatch):
    monkeypatch.setattr(c,'MIN_HOST_DELAY',0)
    s=Session({'https://bank.example/robots.txt':Response(status=404),
               SOURCE['careers_url']:Response('<title>404 - Page not found</title><p>Welcome to our company</p>')})
    f=c.CompliantFetcher([SOURCE],s)
    assert f.fetch(SOURCE['careers_url']) is None
    assert 'Soft 404' in f.failures[SOURCE['careers_url']]


def test_empty_javascript_shell_is_limited_not_green(monkeypatch):
    monkeypatch.delenv('RENDER_JS',raising=False)
    f=Fetcher({SOURCE['careers_url']:'<html><title>Careers</title><div id="root"></div><script src="app.js"></script></html>'})
    outcome,jobs=c._check_employer(SOURCE,[SOURCE],f,c._Budget(0))
    assert outcome['state']=='partial' and outcome['reason_code']=='javascript_required'
    assert not jobs


def test_company_career_branding_is_not_a_parsed_vacancy_list():
    f=Fetcher({SOURCE['careers_url']:'<h1>Careers</h1><p>Our people are our greatest strength. Explore our values.</p>'})
    outcome,_=c._check_employer(SOURCE,[SOURCE],f,c._Budget(0))
    assert outcome['state']=='partial' and outcome['reason_code']=='listing_not_found'


def test_explicit_no_vacancies_is_a_readable_source():
    f=Fetcher({SOURCE['careers_url']:'<h1>Careers</h1><p>No currently available vacancies.</p>'})
    outcome,_=c._check_employer(SOURCE,[SOURCE],f,c._Budget(0))
    assert outcome['state']=='ok' and outcome['jobs_found']==0


def test_collection_reaches_third_listing_page_and_stops_loops(monkeypatch):
    monkeypatch.setattr(c,'sitemap_candidates',lambda *a,**k:[])
    f=Fetcher({SOURCE['careers_url']:'<h1>Careers</h1><a rel="next" href="?page=2">Next</a>',
        SOURCE['careers_url']+'?page=2':'<h1>Careers</h1><a rel="next" href="?page=3">Next</a>',
        SOURCE['careers_url']+'?page=3':posting()+'<a rel="next" href="?page=2">Next</a>'})
    outcome,jobs=c._check_employer(SOURCE,[SOURCE],f,c._Budget(8))
    assert len(jobs)==1 and outcome['listing_pages']==3
    assert f.urls.count(SOURCE['careers_url']+'?page=2')==1


def test_truncated_listing_scan_is_explicitly_limited():
    f=Fetcher({SOURCE['careers_url']:posting()+'<a rel="next" href="?page=2">Next</a>'})
    outcome,jobs=c._check_employer(SOURCE,[SOURCE],f,c._Budget(0))
    assert jobs and outcome['state']=='partial'
    assert outcome['coverage_limited'] and not outcome['collection_complete']
    assert 'pagination' in outcome['message']


def test_robots_sitemap_declaration_and_published_page_index_are_used(monkeypatch):
    monkeypatch.setattr(c,'MIN_HOST_DELAY',0)
    origin='https://bank.example'
    s=Session({origin+'/robots.txt':Response('User-agent: *\nAllow: /\nSitemap: https://bank.example/map/index.xml'),
        SOURCE['careers_url']:Response('<h1>Careers</h1>'),
        origin+'/map/index.xml':Response('<sitemapindex><sitemap><loc>https://bank.example/page-sitemap.xml</loc></sitemap></sitemapindex>',headers={'Content-Type':'application/xml'}),
        origin+'/sitemap.xml':Response(status=404),
        origin+'/page-sitemap.xml':Response('<urlset><url><loc>https://bank.example/careers/cyber-analyst</loc></url></urlset>',headers={'Content-Type':'application/xml'})})
    f=c.CompliantFetcher([SOURCE],s)
    f.fetch(SOURCE['careers_url'])
    found=c.sitemap_candidates(f,SOURCE['careers_url'])
    assert found==[origin+'/careers/cyber-analyst']
    assert origin+'/map/index.xml' in s.urls


def test_apply_link_uses_nearby_job_card_title():
    html='<article><h3>Senior Officer – Information Security</h3><p>Dhaka, Bangladesh</p><a href="/vacancy/729">View details</a></article>'
    assert c.candidate_links(html,SOURCE['careers_url'])==['https://bank.example/vacancy/729']


def test_render_requests_from_many_collectors_use_one_browser_thread(monkeypatch):
    monkeypatch.setenv('RENDER_JS','1')
    seen=[]
    def fake_render(url,ua,timeout,allow):
        seen.append(threading.get_ident())
        return '<h1>Careers</h1>'
    monkeypatch.setattr(render,'_render_page',fake_render)
    with ThreadPoolExecutor(max_workers=4) as pool:
        values=list(pool.map(lambda n:render.render_page(f'https://bank.example/careers?page={n}',c.UA),range(8)))
    assert all(values) and len(set(seen))==1


def test_smartrecruiters_continues_when_total_is_omitted(monkeypatch):
    monkeypatch.setenv('ATS_MAX_PAGES','2')
    class API:
        def get(self,url,**kwargs):
            if 'params' not in kwargs:return Response(data={'jobAd':{'sections':{}}})
            offset=kwargs['params']['offset']
            rows=[{'id':str(i),'name':'Accountant'} for i in range(100)] if offset==0 else [
                {'id':'last','name':'Information Security Analyst','location':{'city':'Dhaka','country':'Bangladesh'}}]
            return Response(data={'content':rows})
    rows=ats.fetch_board(API(),'smartrecruiters','example',c.UA,lambda title:'Security' in title)
    assert len(rows)==1 and rows[0]['title']=='Information Security Analyst'
    assert not rows.coverage_limited


def test_workday_does_not_drop_roles_after_first_twenty_five(monkeypatch):
    monkeypatch.setattr(ats,'robots_ok',lambda *a:True)
    monkeypatch.setattr(ats.time,'sleep',lambda n:None)
    monkeypatch.setenv('ATS_MAX_DETAILS','2')
    class API:
        def post(self,url,**kwargs):
            query=kwargs['json'];start=query['offset']
            rows=[{'title':'Cyber Security Analyst','externalPath':f'/job/Dhaka/R{i}','locationsText':'Dhaka, Bangladesh'}
                  for i in range(start,min(start+20,36))] if query['searchText']=='security' else []
            return Response(data={'jobPostings':rows,'total':36 if query['searchText']=='security' else 0})
        def get(self,url,**kwargs):return Response(data={'jobPostingInfo':{'jobDescription':'Detect threats'}})
    rows=ats.fetch_board(API(),'workday','example|wd3|careers',c.UA,lambda title:True)
    assert len(rows)==36
    assert rows.coverage_limited and 'ATS_MAX_DETAILS' in ' '.join(rows.coverage_notes)


def test_malformed_success_payload_is_not_an_empty_success():
    class API:
        def get(self,*args,**kwargs):return Response(data={'error':'temporarily unavailable'})
    with pytest.raises(ValueError,match='jobs array'):
        ats.fetch_board(API(),'workable','example',c.UA,lambda title:True)


def test_failure_reason_does_not_call_robots_policy_an_outage():
    reason,hint=c.source_failure_reason('robots.txt disallows this path')
    assert reason=='robots_disallowed' and 'published feed' in hint


def test_busy_employer_cannot_consume_other_employers_reserved_requests():
    pool=c._FairBudgetPool(8,3)
    first,second,third=[pool.source(i) for i in range(3)]
    assert sum(first.take() for _ in range(8))==4
    assert second.take() and second.take()
    assert third.take() and third.take()
    assert not third.take()


def test_unused_employer_budget_is_recycled():
    pool=c._FairBudgetPool(6,3)
    first,second,third=[pool.source(i) for i in range(3)]
    first.release()
    assert sum(second.take() for _ in range(6))==4
    assert third.take() and third.take()


def test_pdf_paths_with_download_query_and_document_suffix_are_discovered():
    html='''<a href="/documents/Job.pdf/1234?t=99">Recruitment of Security Analyst</a>
            <a href="/download.php?file=circular.pdf">Recruitment circular</a>
            <a href="/products/notpdf.jpg">Security product</a>'''
    found=c.circular_pdf_links(html,SOURCE['careers_url'])
    assert found==['https://bank.example/documents/Job.pdf/1234?t=99',
                   'https://bank.example/download.php?file=circular.pdf']


def test_short_server_rendered_vacancy_is_not_mistaken_for_empty_app_shell():
    html=posting()+''.join('<script src="analytics.js"></script>' for _ in range(4))
    assert not render.looks_js_rendered(html)
    assert not render.looks_js_rendered('<div id="app"><h1>Careers</h1>No jobs available now.</div>')


def test_unreadable_vacancy_detail_is_not_complete_coverage():
    f=Fetcher({SOURCE['careers_url']:'<h1>Careers</h1><a href="/jobs/security-analyst">Information Security Analyst</a>'})
    outcome,jobs=c._check_employer(SOURCE,[SOURCE],f,c._Budget(4))
    assert not jobs and outcome['state']=='partial'
    assert not outcome['collection_complete']
    assert 'unavailable job detail' in outcome['message']


def test_unreadable_pdf_circular_is_not_complete_coverage():
    f=Fetcher({SOURCE['careers_url']:'<h1>Careers</h1><a href="/recruitment.pdf">Recruitment circular</a>'})
    f.fetch_pdf=lambda url:None
    outcome,_=c._check_employer(SOURCE,[SOURCE],f,c._Budget(4))
    assert outcome['state']=='partial' and 'unavailable PDF' in outcome['message']


def test_inpage_vacancies_anchor_does_not_spend_a_second_fetch():
    assert not c.discover_career_links('<a href="#vacancies">Current vacancies</a>',SOURCE['careers_url'])


@pytest.mark.parametrize('provider',['greenhouse','lever','ashby'])
def test_main_ats_api_error_payload_is_not_reported_as_zero_openings(provider,monkeypatch):
    monkeypatch.setattr(c,'get_json',lambda *args:[])
    class API:
        def get(self,*args,**kwargs):return Response(data={'error':'temporarily unavailable'})
    jobs,health=c.ats_jobs(API(),[SOURCE],discovered=[{'company':'Example Bank','provider':provider,'board_token':'example'}])
    assert not jobs and health[0]['state']=='error'
