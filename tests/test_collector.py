import json
from pathlib import Path
from collector.collect import (
    clean_text, deduplicate, find_skills, get_ld, is_relevant,
    live_filter, list_greenhouse, list_lever, now_bd, scrape_official_job,
    indexed_result_to_job, valid_url, CompliantFetcher
)
from bs4 import BeautifulSoup

ROOT=Path(__file__).resolve().parents[1]
SOURCES=json.loads((ROOT/'data/sources.json').read_text())


def test_source_data():
    sources=SOURCES
    assert len(sources) >= 120
    assert len([s for s in sources if s['sector']=='Banking'])>=55
    assert len([s for s in sources if s['sector']=='Job portal'])>=12
    assert len({s['id'] for s in sources})==len(sources)
    assert all(valid_url(s['website']) or (not s['website'] and s['mode']=='directory') for s in sources)


def test_job_data():
    data=json.loads((ROOT/'data/jobs.json').read_text())
    assert len(data['jobs'])>=1
    for j in data['jobs']:
        for field in ('id','title','company','skills','source','source_url','apply_url','description_status','company_sector'):
            assert field in j
        assert valid_url(j['apply_url'])
        assert is_relevant(j['title'],j.get('description',''))


def test_security_relevance():
    assert is_relevant('Information Security Manager')
    assert is_relevant('Senior Cybersecurity Analyst')
    assert is_relevant('Penetration Tester')
    assert not is_relevant('Security Guard')
    assert not is_relevant('Physical Security Supervisor')
    assert not is_relevant('Account Manager')
    assert 'API Security' in find_skills('OWASP API Security Top 10 and Burp Suite')


def test_url_safety():
    assert not valid_url('javascript:alert(1)')
    assert not valid_url('http://127.0.0.1:8000/admin')
    assert not valid_url('http://localhost:8080')
    assert not valid_url('https://user:pass@example.com')
    assert valid_url('https://www.bkash.com/careers')
    fetcher=CompliantFetcher(SOURCES)
    assert not fetcher.is_official_allowed('https://bd.linkedin.com/jobs/view/123')
    assert not fetcher.is_official_allowed('https://bdjobs.com/h/details/123')
    assert fetcher.is_official_allowed('https://www.grameenphone.com/about/career')
    assert not fetcher.is_official_allowed('https://some-random-example.com/careers')


def test_jsonld_parse():
    doc='''<html><head><script type="application/ld+json">{
    "@context":"https://schema.org","@type":"JobPosting", "title":"Senior Application Security Engineer",
    "description":"Review web and mobile applications, lead API security penetration testing and vulnerability assessments.",
    "datePosted":"2026-11-04","validThrough":"2026-11-24",
    "hiringOrganization":{"@type":"Organization","name":"Example Company","logo":"https://example.com/logo.png"},
    "jobLocation":{"@type":"Place","address":{"addressLocality":"Dhaka","addressCountry":"BD"}},
    "employmentType":"FULL_TIME",
    "url":"https://example.com/jobs/security-engineer"}
    </script></head><body></body></html>'''
    soup=BeautifulSoup(doc,'lxml')
    assert len(get_ld(soup))==1
    results=scrape_official_job(doc,'https://example.com/jobs/security-engineer',SOURCES)
    assert len(results)==1
    j=results[0]
    assert j['company']=='Example Company'
    assert j['deadline']=='2026-11-24'
    assert j['description_status']=='Official excerpt' or j['description_status']=='Full description'
    assert j['company_logo_url']=='https://example.com/logo.png'
    assert 'Dhaka' in j['location']
    assert 'API Security' in j['skills']


def test_search_index_does_not_require_direct_fetch():
    result={'title':'Information Security Engineer at Sample Employer | LinkedIn','url':'https://bd.linkedin.com/jobs/view/example-security-job-111','description':'A role focused on EDR and DLP for a Bangladesh based company.'}
    job=indexed_result_to_job(result,SOURCES)
    assert job is not None
    assert job['company']=='Sample Employer'
    assert job['description_status']=='Search excerpt'
    assert job['source']=='LinkedIn index'


def test_public_ats_normalization():
    greenhouse={'jobs':[{'title':'Cybersecurity Manager','absolute_url':'https://boards.greenhouse.io/acme/jobs/234',
       'location':{'name':'Dhaka, Bangladesh'},'content':'Lead information security and risk management.',
       'first_published':'2026-11-05T10:00:00Z'}]}
    assert len(list_greenhouse(greenhouse,'Example',SOURCES))==1
    lever=[{'text':'Security Engineer','hostedUrl':'https://jobs.lever.co/acme/123',
       'descriptionPlain':'Develop security scanning, vulnerability management and secure CI/CD.',
       'categories':{'location':'Bangladesh','commitment':'Full-time'}}]
    assert len(list_lever(lever,'Example',SOURCES))==1


def test_expired_items_are_not_shown():
    jobs=[{'company':'Example','title':'SOC Analyst','deadline':'2020-01-01','posted_at':'2020-01-01','collected_at':'2020-01-01'},
          {'company':'Example','title':'Security Engineer','deadline':'2999-01-01','posted_at':'','collected_at':now_bd().date().isoformat()}]
    assert len(live_filter(jobs,45))==1


def test_duplicate_crosspostings_choose_detail():
    candidates=[{'company':'Example Ltd.','title':'Cyber Security Analyst','description':'Brief','verification_level':'Search indexed (unverified)','deadline':'',},
                {'company':'Example Ltd.','title':'Cyber Security Analyst','description':'Full details from company website here','verification_level':'Official structured data','deadline':'2026-12-01'}]
    result=deduplicate(candidates)
    assert len(result)==1
    assert result[0]['verification_level']=='Official structured data'


def test_geographic_scope_and_explicit_closure():
    from collector.collect import bangladesh_relevance
    assert bangladesh_relevance('Dhaka, Bangladesh')
    assert bangladesh_relevance('BD')
    assert bangladesh_relevance('Remote', 'Remote within Bangladesh')
    assert not bangladesh_relevance('Remote', 'Work from anywhere globally')
    assert not bangladesh_relevance('San Francisco, CA', 'Lead an AWS security team')
    assert not bangladesh_relevance('New York, USA', 'Bangladesh applicants may be considered')
    assert indexed_result_to_job({'url':'https://www.linkedin.com/jobs/view/999','title':'Cloud Security Engineer', 'description':'San Francisco company is hiring an experienced engineer.'}, SOURCES) is None
    assert indexed_result_to_job({'url':'https://bd.linkedin.com/jobs/view/999','title':'Security Analyst in Bangladesh', 'description':'No longer accepting applications'}, SOURCES) is None


def test_foreign_ats_listings_are_filtered():
    rows={'jobs':[{'title':'Security Engineer','absolute_url':'https://boards.greenhouse.io/example/jobs/7','location':{'name':'New York, USA'},'content':'Build our security systems.'},
                  {'title':'SOC Analyst','absolute_url':'https://boards.greenhouse.io/example/jobs/9','location':{'name':'Dhaka'},'content':'Investigate incidents.'}]}
    jobs=list_greenhouse(rows,'Example',SOURCES)
    assert len(jobs)==1 and jobs[0]['title']=='SOC Analyst'
    lever=[{'text':'Security Engineer','hostedUrl':'https://jobs.lever.co/example/9','descriptionPlain':'Protect infrastructure','categories':{'location':'Singapore'}}]
    assert not list_lever(lever,'Example',SOURCES)


def test_robots_host_allowlist_normalization():
    from collector.collect import same_host_or_subdomain
    assert same_host_or_subdomain('webster.com', 'www.webster.com')
    assert same_host_or_subdomain('careers.webster.com', 'www.webster.com')
    assert not same_host_or_subdomain('webster.com.attacker.tld', 'www.webster.com')
