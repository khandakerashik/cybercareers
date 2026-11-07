"""Regression tests for job retention, worldwide-eligibility and extra sources."""
from __future__ import annotations

import json

from collector import collect as c
from collector import free_feeds as f

SOURCES = [{'name':'Demo Bank','sector':'Banking','website':'https://bank.example',
            'careers_url':'https://bank.example/careers','mode':'career'}]


def test_numeric_timezone_and_location_confidence():
    assert f.eligible_location([], [6]) == 'Worldwide / Bangladesh eligible'
    assert f.eligible_location([], ['+06:00']) == 'Worldwide / Bangladesh eligible'
    assert f.eligible_location([], [-4]) is None
    assert f.eligible_location(None, None, allow_unknown=True).startswith('Location not specified')
    assert f.text_location_eligibility('', allow_unknown=True).startswith('Location not specified')
    assert f.text_location_eligibility('Remote', allow_unknown=True).startswith('Location not specified')
    assert f.text_location_eligibility('EU only', allow_unknown=True) is None
    assert f.text_location_eligibility('APAC', allow_unknown=True).startswith('Regional')
    assert f.confidence('Regional (APAC)') == 'regional'
    assert f.confidence('Location not specified — verify') == 'unconfirmed'


def test_publisher_unknown_remote_stays_visible_but_unconfirmed():
    rows={'jobs':[{'title':'Information Security Manager','company_name':'Example',
                   'description':'Security governance and enterprise risk management',
                   'candidate_required_location':'Remote',
                   'url':'https://remotive.com/remote-jobs/security/example'}]}
    found=f.parse_remotive(rows,SOURCES)
    assert len(found)==1
    assert found[0]['eligibility_confidence']=='unconfirmed'
    assert 'verify' in found[0]['eligibility'].lower()


def test_himalayas_worldwide_and_bd_query_both_issued_without_paid_key():
    class Response:
        def raise_for_status(self):pass
        def json(self):return {'jobs': []}
    class FakeSession:
        def __init__(self):self.seen=[]
        def get(self,url,**kwargs):self.seen.append((url,kwargs));return Response()
    session=FakeSession()
    _,status,_=f.collect_public_feeds(session,SOURCES,{},clock=2000000000,queries_per_run=2)
    queries=[opt.get('params',{}) for url,opt in session.seen if 'himalayas.app' in url]
    assert len(queries)==4
    assert any(q.get('worldwide')=='true' for q in queries)
    assert any(q.get('country')=='BD' for q in queries)
    assert any(x['name']=='Himalayas' and x['requests']==4 for x in status)
    assert all('Authorization' not in opt.get('headers',{}) for _,opt in session.seen)


def test_archive_retained_even_with_no_successful_new_feed(tmp_path,monkeypatch):
    monkeypatch.setattr(c,'DATA',tmp_path)
    (tmp_path/'sources.json').write_text('[]')
    old=c.new_job(title='SOC Analyst', company='Example Bank',
                 url='https://bank.example/jobs/1',source='Official employer',sources=[],
                 posted='2022-01-01',deadline='2023-01-01',
                 description='Review SOC alerts and suspicious events.')
    unverified=c.new_job(title='Information Security Engineer',company='Example Bank',
                 url='https://bank.example/jobs/2',source='Official employer',sources=[],
                 posted='2022-01-01',description='Manage information security for the bank.')
    unverified['last_seen_at']='2022-02-02'
    (tmp_path/'jobs.json').write_text(json.dumps({'jobs':[old,unverified]}))
    monkeypatch.setattr(c,'coverage_round',lambda *args,**kwargs:([],[]))
    monkeypatch.setattr(c,'ats_jobs',lambda *args,**kwargs:([],[]))
    monkeypatch.setattr(f,'collect_public_feeds',lambda *args,**kwargs:([],[],{}))
    report=c.run(max_career_pages=0)
    kept=c.get_json(tmp_path/'jobs.json',{})['jobs']
    assert len(kept)==2
    assert report['jobs_count']==2
    assert report['archived_expired']==1
    assert report['older_unverified']==1
    assert {j['vacancy_status'] for j in kept}=={'expired','older_unverified'}


def test_two_requisitions_with_same_title_are_kept():
    first=c.new_job(title='Cybersecurity Analyst',company='Acme',
       url='https://acme.example/jobs/111',source='Official employer',sources=[])
    second=c.new_job(title='Cybersecurity Analyst',company='Acme',
       url='https://acme.example/jobs/222',source='Official employer',sources=[])
    assert first['id']!=second['id']
    assert len(c.deduplicate([first,second]))==2
    duplicate=first.copy()
    duplicate['description']='Richer official job details and responsibilities.'
    assert len(c.deduplicate([first,duplicate]))==1


def test_published_ats_discovery_not_guessing_tokens():
    html='''<a href="https://jobs.lever.co/realsecurity/jobs/123">Security jobs</a>
             <a href="https://jobs.ashbyhq.com/verifiedcompany/engineering">Vacancies</a>
             <a href="https://boards.greenhouse.io/demobank/jobs/1982">Bank vacancies</a>
             <a href="https://jobs.lever.co.evil.example/steal">Evil</a>'''
    boards=c.discover_ats_links(html,'https://bank.example/careers','Demo Bank')
    assert {(x['provider'],x['board_token']) for x in boards}=={
       ('lever','realsecurity'),('ashby','verifiedcompany'),('greenhouse','demobank')}
    assert all(x['company']=='Demo Bank' for x in boards)


def test_official_bank_pdf_circular_links_and_parser(monkeypatch):
    html='''<a href="/careers/info-security-recruitment.pdf">IT security job circular</a>
    <a href="https://bad.example/sensitive-job.pdf">Other</a>'''
    links=c.circular_pdf_links(html,'https://bank.example/careers')
    assert links==['https://bank.example/careers/info-security-recruitment.pdf',
                   'https://bad.example/sensitive-job.pdf']
    # A compliant fetcher will reject bad.example even though it appears in HTML.
    fetcher=c.CompliantFetcher(SOURCES)
    assert fetcher.is_official_allowed(links[0])
    assert not fetcher.is_official_allowed(links[1])
    import pypdf
    class FakePage:
        def extract_text(self):
            return ('Recruitment circular: please submit applications by the deadline\n'
                    'Senior Information Security Officer\nSecurity Guard\n'
                    'Experience in cybersecurity monitoring and incident response\n')
    class FakeReader:
        def __init__(self,*a,**kw):self.pages=[FakePage()]
    monkeypatch.setattr(pypdf,'PdfReader',FakeReader)
    jobs=c.parse_pdf_circular(b'%PDF-fake',links[0],'Demo Bank',SOURCES)
    assert len(jobs)==1
    assert jobs[0]['source']=='Official PDF circular'
    assert jobs[0]['title']=='Senior Information Security Officer'


def test_recruitment_rss_parses_only_relevant_titles_on_official_domain():
    xml='''<rss><channel><item><title>Information Security Specialist</title>
      <link>https://bank.example/careers/infosec-specialist</link>
      <description>Information security monitoring and ISO 27001</description></item>
      <item><title>Security Guard</title><link>https://bank.example/jobs/guard</link></item>
      <item><title>SOC Analyst</title><link>https://attacker.example/jobs/steal</link></item>
      </channel></rss>'''
    parsed=c.parse_job_rss(xml,'https://bank.example/careers/rss.xml','Demo Bank',SOURCES)
    assert len(parsed)==1
    assert parsed[0]['title']=='Information Security Specialist'


def test_seeded_worldwide_leads_have_original_publisher_urls():
    content=c.get_json(c.ROOT/'data/jobs.json',{})
    jobs=[j for j in content.get('jobs',[]) if j.get('region')=='International']
    assert len(jobs)>=10
    assert all(j.get('eligibility_confidence')=='confirmed' for j in jobs)
    assert all(c.valid_url(j['apply_url']) for j in jobs)
    assert all(j['source'] in ('Himalayas','Remotive') for j in jobs)


def test_exclude_anywhere_only_in_foreign_country():
    from collector.free_feeds import text_location_eligibility
    for text in ('Anywhere in the United States', 'Anywhere in Canada', 'Anywhere within the UK'):
        assert text_location_eligibility(text, allow_unknown=True) is None
    assert text_location_eligibility('Work from anywhere', allow_unknown=True).startswith('Worldwide')


def test_expired_himalayas_removed_per_api_terms():
    from collector.collect import annotate_freshness
    records = [
        {'title':'Cloud Security Engineer', 'source':'Himalayas', 'deadline':'2020-01-01'},
        {'title':'Cybersecurity Analyst', 'source':'Jobicy', 'deadline':'2020-01-01'},
        {'title':'InfoSec Manager', 'source':'Himalayas', 'deadline':'2099-01-01'},
    ]
    out=annotate_freshness(records)
    assert len(out)==2
    assert [item['title'] for item in out]==['Cybersecurity Analyst','InfoSec Manager']
    assert out[0]['vacancy_status']=='expired'
