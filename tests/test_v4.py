"""CyberCareers BD v4 reliability, persistence, bilingual search, HTTP tests."""
from __future__ import annotations

import json
from pathlib import Path

from collector import collect as c
from collector import free_feeds as f
from collector.telemetry import CollectionTelemetry, IncrementalJobStore
from server.app import public_path


def test_history_retains_only_last_ten_actual_attempts(tmp_path):
    updates=[]
    tracker=CollectionTelemetry(tmp_path,total=13,status_callback=updates.append)
    for i in range(12):
        tracker.completed(source_id='demo-bank',name='Demo Bank',sector='Banking',mode='Official employer',
                          state='ok' if i%2==0 else 'error',jobs=i%3,message=f'Attempt {i}')
    tracker.completed(source_id='demo-bank',name='Demo Bank',sector='Banking',mode='Official employer',state='cached')
    tracker.finish()
    health=json.loads((tmp_path/'source_health.json').read_text())
    items=health['sources']['demo-bank']['history']
    assert len(items)==10
    assert items[0]['message']=='Attempt 2' and items[-1]['message']=='Attempt 11'
    assert [x['result'] for x in items]==['success','failed']*5
    assert health['sources']['demo-bank']['successes']==5
    progress=json.loads((tmp_path/'progress.json').read_text())
    assert progress['total']==13 and progress['checked']==13 and progress['remaining']==0
    assert progress['succeeded']==6 and progress['failed']==6 and progress['skipped']==1
    assert progress['running'] is False and progress['phase']=='completed'
    assert updates[0]['checked']==0 and updates[-1]['checked']==13


def test_success_without_matches_is_healthy(tmp_path):
    t=CollectionTelemetry(tmp_path,total=1)
    t.completed(source_id='no-jobs',name='Career homepage',sector='Telecom',mode='Official employer',state='ok',jobs=0)
    h=json.loads((tmp_path/'source_health.json').read_text())['sources']['no-jobs']
    assert h['last_result']=='success'
    assert h['jobs_found_last_check']==0
    assert h['history']==[h['history'][0]]


def test_persist_job_json_incrementally_and_retain_rich_details(tmp_path):
    path=tmp_path/'jobs.json'
    store=IncrementalJobStore(path)
    original=c.new_job(title='Information Security Officer',company='Example Bank',source='Official employer',
                       url='https://careers.example.org/jobs/a1',sources=[],
                       description='Official job details with security audits, GRC, vulnerability management, and many other responsibilities.',
                       deadline='2026-12-30',requirements=['CISSP'],responsibilities=['Security program ownership'],
                       poster_url='https://cdn.example.org/image.png',
                       verification_level='Official structured data')
    assert store.merge_batch([original])==1
    persisted=json.loads(path.read_text())
    assert len(persisted['jobs'])==1
    assert persisted['jobs'][0]['requirements']==['CISSP']
    assert persisted['jobs'][0]['poster_url']=='https://cdn.example.org/image.png'
    weaker=original.copy()
    weaker.update(description='Only title shown',requirements=[],poster_url='',
                  verification_level='Search indexed (unverified)')
    assert store.merge_batch([weaker])==0
    persisted=json.loads(path.read_text())
    assert persisted['jobs'][0]['description']==original['description']
    assert persisted['jobs'][0]['requirements']==['CISSP']
    other=c.new_job(title='SOC Analyst',company='Another Bank',source='Official employer',
                    url='https://careers.example.org/jobs/a2',sources=[],description='SOC alert investigations')
    assert store.merge_batch([other])==1
    assert len(json.loads(path.read_text())['jobs'])==2


def test_bengali_security_relevance_and_non_cyber_exclusions():
    assert c.is_relevant('সাইবার নিরাপত্তা কর্মকর্তা নিয়োগ')
    assert c.is_relevant('তথ্য নিরাপত্তা বিশেষজ্ঞ')
    assert c.is_relevant('ইনফরমেশন সিকিউরিটি অফিসার')
    assert c.is_relevant('ব্যবস্থাপক পদে নিয়োগ','তথ্য নিরাপত্তা বিভাগে প্রয়োজনীয় অভিজ্ঞতা আবশ্যক')
    assert not c.is_relevant('সিকিউরিটি গার্ড নিয়োগ')
    assert not c.is_relevant('নিরাপত্তা প্রহরী চাকরি')
    assert not c.is_relevant('নিরাপত্তা বিভাগে প্রহরী পদে নিয়োগ')
    assert not c.is_relevant('Account Manager')
    assert len(c.BANGLA_SEARCH_TERMS)>=10


def test_source_directory_has_banks_telcos_portals_social_and_no_central_bank():
    sources=json.loads((c.DATA/'sources.json').read_text(encoding='utf-8'))
    names={s['name'].casefold() for s in sources}
    assert 'bangladesh bank' not in names
    assert 'bangladesh bank e-recruitment' not in names
    assert len(sources)>=185
    assert len([s for s in sources if s['sector']=='Banking'])>=60
    assert len([s for s in sources if s['sector']=='Telecom'])>=10
    assert any('linkedin' in s['name'].lower() for s in sources)
    assert any('facebook' in s['name'].lower() for s in sources)
    assert all(s['sector']=='Social media' for s in sources if 'Facebook' in s['name'])
    checked=c.selected_employers(sources,999)
    assert not any(s['name'].casefold()=='bangladesh bank' for s in checked)
    assert len([s for s in checked if s['sector']=='Banking'])>=60
    assert all(s['sector'] not in ('Social media','Job portal') for s in checked)


def test_bilingual_discovery_queries_json_safe():
    queries=json.loads((c.DATA/'search_queries.json').read_text(encoding='utf-8'))
    assert len(queries)>=40
    assert any(any('\u0980'<=ch<='\u09ff' for ch in x['query']) for x in queries)
    assert any('LinkedIn' in x.get('query','') or 'linkedin' in x.get('search_url','').lower() for x in queries)
    assert all(c.valid_url(x['search_url']) for x in queries)


def test_telemetry_can_run_dry_without_writes(tmp_path):
    updates=[]
    tracker=CollectionTelemetry(tmp_path,total=2,persist=False,status_callback=updates.append)
    tracker.phase('employers','Checking')
    tracker.completed(source_id='x',name='X',sector='Banking',mode='Official employer',state='error')
    tracker.finish()
    assert not list(tmp_path.glob('*.json'))
    assert updates[-1]['checked']==1 and updates[-1]['remaining']==1


def test_ats_dynamic_total_and_complete_progress(tmp_path):
    t=CollectionTelemetry(tmp_path,total=2)
    t.extend_total(2)
    for i in range(4):
        t.completed(source_id=f'x{i}',name=f'X{i}',sector='ATS boards',mode='ATS API',state='ok',jobs=0)
    t.finish()
    assert t.progress['checked']==t.progress['total']==4
    assert t.progress['remaining']==0


def test_local_http_allowlist_for_v4_health_progress_and_queries():
    for name in ('source_health.json','progress.json','search_queries.json','jobs.json'):
        assert public_path('/data/'+name)==c.DATA/name
    for path in ('/data/../.env','/data/ats.json','/data/extra.json','/.env'):
        assert public_path(path) is None


def test_public_feed_reports_one_health_outcome_each_for_success_failure_and_cache():
    class Resp:
        def __init__(self,url): self.url=url
        def raise_for_status(self): return None
        def json(self):return {'jobs':[]}
    class FakeSession:
        def get(self,url,**kwargs):
            if 'remotive.com' in url:
                raise __import__('requests').ConnectionError('offline')
            return Resp(url)
    callbacks=[]
    _,statuses,cache=f.collect_public_feeds(FakeSession(),[],{},clock=2_000_000_000,
                                            queries_per_run=1,on_source=lambda outcome,jobs:callbacks.append(outcome))
    assert len(statuses)==len(f.PROVIDERS)==len(callbacks)
    assert {x['name']:x['state'] for x in statuses}['Remotive']=='error'
    assert {x['name']:x['state'] for x in statuses}['Jobicy']=='ok'
    callbacks=[]
    _,second,_=f.collect_public_feeds(FakeSession(),[],cache,clock=2_000_000_100,
                                      queries_per_run=1,on_source=lambda outcome,jobs:callbacks.append(outcome))
    assert len(callbacks)==len(f.PROVIDERS)
    assert {x['name']:x['state'] for x in second}['Jobicy']=='cached'


def test_source_progress_is_available_from_controller():
    from server.app import RefreshController
    control=RefreshController()
    control._handle_progress({'running':True,'total':190,'checked':42,'remaining':148,'new_jobs':4})
    progress=control.status()['progress']
    assert progress['checked']==42 and progress['remaining']==148


def test_official_html_extracts_detailed_bangla_and_english_sections():
    from bs4 import BeautifulSoup
    html = '''<h2>Additional Requirements</h2><ul><li>Experience with cybersecurity operations</li><li>Experience with cloud security and threat detection</li></ul>
    <h2>Job Responsibilities</h2><ul><li>Investigate cybersecurity incidents and coordinate incident response</li></ul>'''
    reqs, duties=c.extract_role_sections(BeautifulSoup(html,'lxml'))
    assert any('cloud security' in q for q in reqs)
    assert any('Investigate' in q for q in duties)
    assert 'Information Security' in c.find_skills('তথ্য নিরাপত্তা বিভাগ')
    assert 'Penetration Testing' in c.find_skills('পেনিট্রেশন টেস্টিং')
    assert 'Network Security' in c.find_skills('নেটওয়ার্ক নিরাপত্তা')


def test_verified_telecom_career_urls():
    sources={s['name']:s for s in json.loads((c.DATA/'sources.json').read_text())}
    assert sources['Fiber@Home']['careers_url'].endswith('/career')
    assert sources['Link3 Technologies']['careers_url'].endswith('/career')
    assert sources['Summit Communications']['careers_url'].endswith('/career')


def test_http_200_challenge_page_is_not_marked_a_success():
    class Response:
        ok=True
        status_code=200
        headers={'content-type':'text/html'}
        content=b'<html><head><title>Just a moment...</title></head><body>Checking</body></html>'
        text=content.decode()
    class Session:
        headers={}
        def get(self,*args,**kwargs):return Response()
    src={'name':'Example','sector':'Banking','mode':'career','website':'https://demo.example.org','careers_url':'https://demo.example.org/jobs'}
    fetch=c.CompliantFetcher([src],Session())
    fetch.robots_allow=lambda u: True
    page=fetch.fetch(src['careers_url'])
    assert page is None
    assert 'challenge' in fetch.failures[src['careers_url']].lower()


def test_end_to_end_offline_scan_persists_progress_and_source_health(tmp_path, monkeypatch):
    # All sources are simulated; the runner must never make a network request.
    monkeypatch.setattr(c, 'DATA', tmp_path)
    src={'id':'test-bank','name':'Testing Bank','sector':'Banking','mode':'career',
         'website':'https://examplebank.org','careers_url':'https://examplebank.org/careers'}
    (tmp_path/'sources.json').write_text(json.dumps([src]))
    (tmp_path/'jobs.json').write_text(json.dumps({'jobs':[]}))
    collected=c.new_job(title='সাইবার নিরাপত্তা কর্মকর্তা',company='Testing Bank',
        url='https://examplebank.org/careers/cybersecurity-123',source='Official employer',
        description='ব্যাংকের তথ্য নিরাপত্তা বিভাগে সাইবার নিরাপত্তা তদারকি',sources=[src])

    def faux_feeds(session, sources, state, *, force, queries_per_run, on_source):
        from collector.free_feeds import PROVIDERS
        statuses=[]
        for provider in PROVIDERS:
            row={'source_id':'feed:'+provider,'name':provider,'sector':'Remote job feed',
                 'mode':'Free publisher feed','state':'ok','jobs_found':0,'requests':1}
            on_source(row,[])
            statuses.append(row)
        return [],statuses,{}

    def faux_employers(sources, fetcher, limit, *, detail_budget, on_source):
        row={'source_id':'test-bank','name':'Testing Bank','sector':'Banking',
             'mode':'Official employer','state':'ok','jobs_found':1}
        on_source(row,[collected])
        # Must be saved while the employer callback runs, not only at the end.
        db=json.loads((tmp_path/'jobs.json').read_text())
        assert len(db['jobs'])==1 and db['jobs'][0]['title']==collected['title']
        return [collected],[row]

    monkeypatch.setattr(f,'collect_public_feeds',faux_feeds)
    monkeypatch.setattr(c,'coverage_round',faux_employers)
    monkeypatch.setattr(c,'ats_jobs',lambda *args,**kwargs:([],[]))
    snapshots=[]
    report=c.run(max_queries=0,max_career_pages=1,max_detail_pages=0,on_progress=snapshots.append)
    progress=json.loads((tmp_path/'progress.json').read_text())
    health=json.loads((tmp_path/'source_health.json').read_text())
    assert progress['checked']==progress['total']==len(f.PROVIDERS)+1
    assert progress['remaining']==0 and progress['new_jobs']==1
    assert health['sources']['test-bank']['last_result']=='success'
    assert health['sources']['test-bank']['history'][-1]['jobs_found']==1
    assert report['jobs_count']==1 and report['new_jobs_count']==1
    assert snapshots[-1]['running'] is False


def test_migration_from_older_json_preserves_existing_database(tmp_path):
    from collector.import_existing import import_existing_jobs
    destination=tmp_path/'jobs.json'
    previous=tmp_path/'v3-jobs.json'
    base=c.new_job(title='Information Security Manager',company='Old Bank',
                   url='https://oldbank.example/jobs/1',source='Official employer',sources=[])
    extra=c.new_job(title='Cloud Security Engineer',company='Another Bank',
                    url='https://anotherbank.example/jobs/2',source='Official employer',sources=[])
    blocked=c.new_job(title='SOC Analyst',company='Bangladesh Bank',
                      url='https://central.example/jobs/1',source='Official employer',sources=[])
    destination.write_text(json.dumps({'jobs':[base]}))
    previous.write_text(json.dumps({'jobs':[base,extra,blocked]}))
    preview=import_existing_jobs(previous,target=destination,dry_run=True)
    assert preview['database_total']==2
    assert len(json.loads(destination.read_text())['jobs'])==1
    actual=import_existing_jobs(previous,target=destination)
    assert actual['accepted_from_old_file']==2 and actual['added']==1
    assert len(json.loads(destination.read_text())['jobs'])==2
