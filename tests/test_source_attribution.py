"""Original source attribution survives collection, imports and UI filtering."""
import json
from pathlib import Path

from collector.collect import deduplicate, job_source_attribution, new_job

ROOT = Path(__file__).resolve().parents[1]


def test_source_domain_follows_original_listing_not_application_destination():
    job = new_job(title='Information Security Analyst', company='Demo Bank',
        source='Official employer', url='https://jobs.demo-bank.example/career/role-9',
        apply_url='https://external-ats.example/form/role-9', sources=[])
    assert job['source_domain'] == 'jobs.demo-bank.example'
    assert job['source_name'] == 'Demo Bank · official careers'
    assert job['source_url'] != job['apply_url']


def test_source_publisher_naming_for_portals_and_public_feeds():
    cases = [
        ('LinkedIn index', 'LinkedIn'),
        ('Bdjobs index', 'Bdjobs'),
        ('Himalayas', 'Himalayas'),
        ('Greenhouse public API', 'Greenhouse · Demo Bank'),
        ('Official PDF circular', 'Demo Bank · recruitment circular'),
    ]
    for source, expected in cases:
        got = job_source_attribution(source, 'Demo Bank', 'https://bd.linkedin.com/jobs/view/123')
        assert got['source_name'] == expected
        assert got['source_domain'] == 'bd.linkedin.com'


def test_attribution_preserved_during_duplicate_merge():
    original = new_job(title='Cyber Security Engineer', company='Demo Bank',
        url='https://demo.example/careers/cybersec', source='Official employer', sources=[])
    fuller = original.copy()
    fuller.pop('source_name')
    fuller.pop('source_domain')
    fuller['description'] = 'Rich full job description and application security requirements ' * 10
    fuller['verification_level'] = 'Official structured data'
    merged = deduplicate([original, fuller])
    assert len(merged) == 1
    assert merged[0]['source_name'] == original['source_name']
    assert merged[0]['source_domain'] == original['source_domain']


def test_seeded_job_database_has_publisher_identity_and_original_url():
    payload = json.loads((ROOT/'tests/fixtures/seed_jobs.json').read_text(encoding='utf-8'))
    assert len(payload['jobs']) >= 20
    for job in payload['jobs']:
        assert job['source'] and job['source_name'] and job['source_domain']
        assert job['source_url'].startswith('http')
        assert job['apply_url'].startswith('http')


def test_independent_source_platform_and_site_filters_for_both_geographies():
    html = (ROOT/'index.html').read_text(encoding='utf-8')
    js = (ROOT/'app.js').read_text(encoding='utf-8')
    for input_id in ('sourceSelect','sourceSiteSelect','intlSourceSelect','intlSourceSiteSelect'):
        assert f'id="{input_id}"' in html
        assert f"$('#{input_id}')" in js
    assert 'jobSourceRow(job)' in js
    assert 'jobSourceDomain(j)!==state.intlSourceSite' in js
    assert 'jobSourceDomain(job)!==f.sourceSite' in js
