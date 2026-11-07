"""Offline tests for no-key international feeds and source pacing."""
from pathlib import Path

import pytest

from collector.collect import (CompliantFetcher, discover_career_links,
    get_json, is_relevant, list_ashby, new_job, run)
from collector.free_feeds import (PROVIDERS, collect_public_feeds, eligible_location,
    parse_himalayas, parse_jobicy, parse_remoteok, parse_remotive,
    text_location_eligibility)

SOURCES = [{'name':'Test Bank','sector':'Banking','website':'https://bank.example',
            'careers_url':'https://bank.example/careers','mode':'career'}]


def himalaya_job(**kwargs):
    return {
        'title':'Senior Information Security Engineer','companyName':'Widget Co',
        'description':'Lead API security, vulnerability assessment and penetration testing.',
        'locationRestrictions':[], 'timezoneRestrictions':[],
        'guid':'https://himalayas.app/companies/widget/jobs/security',
        'applicationLink':'https://himalayas.app/apply/widget/security?ref=api',
        'companyLogo':'https://cdn.example/widget.png', 'pubDate': 1793980000,
        **kwargs
    }


def test_himalayas_keeps_required_apply_link_and_explicit_eligibility():
    jobs=parse_himalayas({'jobs':[himalaya_job()]},SOURCES)
    assert len(jobs)==1
    job=jobs[0]
    assert job['source']=='Himalayas' and job['region']=='International'
    assert job['apply_url']=='https://himalayas.app/apply/widget/security?ref=api'
    assert job['source_url'].startswith('https://himalayas.app/')
    assert job['eligibility']=='Worldwide / Bangladesh eligible'
    assert job['company_logo_url']=='https://cdn.example/widget.png'
    assert 'API Security' in job['skills']
    assert job['company_sector']=='International employer'


def test_himalayas_requires_country_and_timezone_eligibility():
    assert eligible_location([],[])=='Worldwide / Bangladesh eligible'
    assert eligible_location([{'alpha2':'BD'}],[])=='Bangladesh eligible'
    assert eligible_location([{'alpha2':'US'}],[]) is None
    assert eligible_location(None,[]) is None
    assert eligible_location([],["UTC-05:00"]) is None
    assert eligible_location([],["UTC+06:00"])=='Worldwide / Bangladesh eligible'
    assert len(parse_himalayas({'jobs':[himalaya_job(locationRestrictions=[{'alpha2':'US'}])]},SOURCES))==0
    assert len(parse_himalayas({'jobs':[himalaya_job(timezoneRestrictions=['UTC-04:00'])]},SOURCES))==0


def test_remotive_and_remoteok_location_restrictions():
    remotive={'jobs':[
       {'title':'Security Engineer','candidate_required_location':'Worldwide','url':'https://remotive.com/remote-jobs/security/test','description':'Investigate incidents and vulnerabilities.'},
       {'title':'Application Security Engineer','candidate_required_location':'US Only','url':'https://remotive.com/remote-jobs/security/us-only'}]}
    jobs=parse_remotive(remotive,SOURCES)
    assert len(jobs)==1 and jobs[0]['eligibility'].startswith('Worldwide')
    remoteok=[{'legal':'free service metadata'},
        {'position':'SOC Analyst','location':'Anywhere','url':'https://remoteok.com/remote-jobs/100','description':'Monitor security events.'},
        {'position':'Information Security Officer','location':'Berlin, Germany','url':'https://remoteok.com/remote-jobs/101','description':'Protect records.'}]
    jobs=parse_remoteok(remoteok,SOURCES)
    assert len(jobs)==1 and jobs[0]['source']=='Remote OK'
    assert text_location_eligibility('APAC (Remote)').startswith('Regional')
    assert text_location_eligibility('Remote (no locations given)') is None


def test_jobicy_canonical_link_salary_sector_and_location():
    jobs=[{'id':1,'url':'https://jobicy.com/jobs/cyber-111',
           'jobTitle':'Senior Cybersecurity Analyst','companyName':'Secure Inc',
           'jobDescription':'<p>Security operations, SIEM, threat hunting and investigations.</p>',
           'jobGeo':'Anywhere','jobLevel':'Senior', 'jobType':['Full-Time'],
           'companyLogo':'https://img.example/logo.png',
           'salaryMin':80000,'salaryMax':120000, 'salaryCurrency':'USD','salaryPeriod':'yearly',
           'pubDate':'2026-11-06T12:00:00+00:00'},
          {'id':2,'url':'https://jobicy.com/jobs/101','jobTitle':'Cybersecurity Engineer','jobGeo':'USA Only'},
          {'id':3,'url':'https://jobicy.com.evil.example/role','jobTitle':'Information Security Analyst','jobGeo':'Anywhere'}]
    parsed=parse_jobicy({'jobs':jobs},SOURCES)
    assert len(parsed)==1
    j=parsed[0]
    assert j['source']=='Jobicy' and j['region']=='International'
    assert j['apply_url']=='https://jobicy.com/jobs/cyber-111'
    assert j['salary']=='USD 80,000–120,000 / yearly'
    assert j['company_sector']=='International employer'
    assert j['employment_type']=='Full-Time'
    assert j['description_status'] in ('Full feed description','Publisher excerpt')


def test_jobicy_handles_missing_and_invalid_salary_without_dropping_job():
    j={'jobTitle':'InfoSec Manager','jobGeo':'Bangladesh','url':'https://jobicy.com/jobs/security-4',
       'salaryMin':'invalid salary number'}
    a=parse_jobicy({'jobs':[j]},SOURCES)
    assert len(a)==1 and a[0]['salary']=='Not disclosed'
    assert a[0]['eligibility']=='Bangladesh eligible'


class FakeResponse:
    status_code=200
    def __init__(self,body): self.body=body; self.content=body if isinstance(body,bytes) else b''
    def raise_for_status(self):pass
    def json(self):return self.body


class FakeSession:
    def __init__(self):self.requests=[]
    def get(self,url,**kwargs):
        self.requests.append((url,kwargs))
        if 'himalayas.app' in url:return FakeResponse({'jobs':[himalaya_job()]})
        if 'remotive.com' in url:return FakeResponse({'jobs':[]})
        if 'remoteok.com' in url:return FakeResponse([])
        if 'jobicy.com' in url:return FakeResponse({'jobs':[]})
        if 'weworkremotely.com' in url:return FakeResponse(b'<rss><channel></channel></rss>')
        if 'workingnomads.com' in url:return FakeResponse([])
        raise AssertionError('Unexpected public API '+url)


def test_hourly_scheduler_keeps_provider_backoff_and_does_not_repoll_too_soon():
    session=FakeSession()
    jobs,health,state=collect_public_feeds(session,SOURCES,{},clock=2_000_000_000,queries_per_run=1)
    assert len(jobs)==2   # The free API returns the same job for BD and worldwide search; global merge deduplicates it.
    assert len(health)==len(PROVIDERS)==6
    assert len(session.requests)==2+1+1+3+2+1  # Himalayas worldwide + Bangladesh, Remotive, Remote OK, Jobicy, WWR x2, Working Nomads
    assert state['Jobicy']['next_check']==2_000_000_000+3600
    assert state['Himalayas']['next_check']==2_000_000_000+86400
    n=len(session.requests)
    _,health,state=collect_public_feeds(session,SOURCES,state,clock=2_000_003_599,queries_per_run=1)
    assert len(session.requests)==n
    assert all(x['state']=='cached' for x in health)
    _,health,state=collect_public_feeds(session,SOURCES,state,clock=2_000_003_601,queries_per_run=1)
    assert len(session.requests)==n+3 and sum(x['state']=='ok' for x in health)==1
    assert next(x for x in health if x['name']=='Himalayas')['state']=='cached'


def test_expanded_security_terms_and_physical_guard_rejection():
    for term in ('Information Security Officer','ICT Risk Analyst','Technology Audit Manager',
                 'SWIFT Security Lead','Threat Intelligence Researcher','DevSecOps Engineer',
                 'Information Systems Security Auditor','CISO', 'SOC Analyst',
                 'IT Governance Specialist', 'Cyber Defense Manager'):
        assert is_relevant(term), term
    assert not is_relevant('Security Guard (Night Shift)')
    assert not is_relevant('Airport Security Agent Guard')


def test_official_career_navigation_stays_on_listed_domain():
    html='''<html><a href="/about">About</a><a href="/careers">Current vacancies</a>
        <a href="https://bank.example.jobs.attacker.test/careers">Apply now</a>
        <a href="https://bank.example/recruitment/jobs">Recruitment</a></html>'''
    found=discover_career_links(html,'https://bank.example/',limit=5)
    assert 'https://bank.example/careers' in found
    assert 'https://bank.example/recruitment/jobs' in found
    assert not any('attacker' in s for s in found)
    fetcher=CompliantFetcher(SOURCES)
    assert fetcher.is_official_allowed('https://bank.example/careers')
    assert not fetcher.is_official_allowed('https://bdjobs.com/job/security')
    assert not fetcher.is_official_allowed('https://bank.example.attacker.com/careers')


def test_ashby_public_board_preserves_apply_url_and_geographic_filter():
    data={'jobs':[
        {'title':'Information Security Analyst','jobUrl':'https://jobs.ashbyhq.com/company/role1',
         'applyUrl':'https://jobs.ashbyhq.com/company/apply1',
         'location':'Dhaka, Bangladesh','descriptionPlain':'Analyze suspicious logins and EDR alerts.'},
        {'title':'SOC Engineer','jobUrl':'https://jobs.ashbyhq.com/company/role2','location':'London, UK'}]}
    out=list_ashby(data,'Company',SOURCES)
    assert len(out)==1 and out[0]['apply_url'].endswith('apply1')


def test_last_seen_refresh_preserves_richer_record(tmp_path,monkeypatch):
    import collector.collect as c
    import collector.free_feeds as f
    monkeypatch.setattr(c,'DATA',tmp_path)
    (tmp_path/'sources.json').write_text('[]')
    old=c.new_job(title='SOC Analyst',company='Bank Demo',url='https://bank.example/jobs/security',source='Official employer',sources=[],
        description='Full official requirements and responsibilities.'*15,
        verification_level='Official structured data')
    old['last_seen_at']='2026-09-01'
    (tmp_path/'jobs.json').write_text(__import__('json').dumps({'jobs':[old]}))
    seen=c.new_job(title='SOC Analyst',company='Bank Demo',url='https://bank.example/jobs/security',source='Official employer',sources=[],
        description='Recent listing excerpt',verification_level='Official page parsed')
    monkeypatch.setattr(c,'coverage_round',lambda *args,**kwargs:([seen],[]))
    monkeypatch.setattr(c,'ats_jobs',lambda *args,**kwargs:([],[]))
    monkeypatch.setattr(f,'collect_public_feeds',lambda *args,**kwargs:([],[],{}))
    report=c.run(max_queries=0,max_career_pages=0)
    saved=c.get_json(tmp_path/'jobs.json',{})['jobs']
    assert report['new_jobs_count']==0
    assert saved[0]['verification_level']=='Official structured data'
    assert saved[0]['last_seen_at']==c.today_iso()
