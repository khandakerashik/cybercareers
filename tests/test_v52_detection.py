"""Regression corpus for false events, occupation ambiguity and vacancy proof."""
from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest

from collector.relevance import assess, strong_terms
from collector.vacancy import assess_record, assess_vacancy, is_portal_job_url


@pytest.mark.parametrize('title', [
    'Cybersecurity Conference 2026 — Dhaka',
    'Information Security Workshop: Apply Now',
    'SOC Analyst Training',
    'Free Penetration Testing Course',
    'Application Security Webinar',
    'Cybersecurity Career Fair',
    'Information Security Awareness Month',
    'How to become a SOC Analyst',
    'SOC Analyst Interview Questions',
    'Cyber Security Engineer Salary Guide',
    'Bank appoints new Chief Information Security Officer',
    '120 Information Security jobs in Bangladesh',
    'Cybersecurity jobs',
    'Cybersecurity Services',
    'Our Information Security Team',
    'সাইবার নিরাপত্তা কর্মশালা',
    'তথ্য নিরাপত্তা প্রশিক্ষণ',
    'সাইবার নিরাপত্তা প্রশিক্ষণে নিবন্ধন করুন',
    'সাইবার নিরাপত্তা সচেতনতা কর্মসূচি',
])
def test_topics_events_and_list_pages_are_not_security_vacancies(title):
    # Even misleading shared navigation or a structured-data label must not
    # rescue a clearly non-vacancy headline.
    desc = 'Careers. Dhaka, Bangladesh. Apply now. SIEM, ISO 27001. Register here.'
    assert not assess(title, desc).relevant
    for kind in ('html', 'feed', 'index', 'jobposting', 'publisher'):
        assert not assess_vacancy(title, desc, 'https://bank.example/careers/cyber', source_kind=kind).vacancy


@pytest.mark.parametrize(('title', 'description'), [
    ('SOC Design Engineer', 'RTL design for semiconductor products.'),
    ('Senior SoC Verification Engineer', 'ASIC, VLSI and system-on-chip testing.'),
    ('Sales Manager at CyberArk', 'Build customer accounts in Dhaka.'),
    ('Head of Security', 'Manage CCTV surveillance, guard force and visitor screening.'),
    ('Security Operations Center Operator', 'CCTV monitoring and physical security patrols.'),
    ('GRC Engineer', 'Glass fibre reinforced concrete and cladding production.'),
    ('Account Manager', 'Our cybersecurity company provides information security, SIEM, SOC and penetration testing.'),
    ('Senior Recruiter', 'The Information Security Division uses SIEM, ISO 27001 and penetration testing.'),
    ('Software Engineer', 'Our company is SOC 2 certified. We value information security and cybersecurity. Develop payment APIs.'),
    ('Office Manager', 'Work with the Information Security Department on employee onboarding.'),
])
def test_hardware_physical_and_boilerplate_false_positives(title, description):
    assert not assess(title, description).relevant


@pytest.mark.parametrize(('title', 'description'), [
    ('Cybersecurity Trainer', 'We are hiring. Full-time. Qualifications: CEH. Apply now.'),
    ('Cybersecurity Bootcamp Instructor', 'Full-time instructor vacancy. Submit your CV.'),
    ('Security Training Specialist', 'Design information security courses and maintain the ISMS. Department: Information Security Team.'),
    ('SOC Analyst (Training Provided)', 'Monitor SIEM alerts and investigate incidents.'),
    ('Hardware Security Engineer', 'Research side channels in SoCs.'),
    ('SoC Security Architect', 'Secure chip design and cryptographic hardware.'),
    ('AI Security Engineer', 'Build LLM security controls and threat models.'),
    ('LLM Security Researcher', 'Assess prompt injection and model risks.'),
    ('Head of Security', 'Lead information security governance and SIEM operations.'),
    ('Senior Principal Officer', 'Place of posting: Information Security Division. SIEM and ISO 27001.'),
    ('Senior Officer', 'Perform penetration testing, vulnerability assessment and incident response. Maintain SIEM rules.'),
    ('ব্যবস্থাপক পদে নিয়োগ', 'তথ্য নিরাপত্তা বিভাগে প্রয়োজনীয় অভিজ্ঞতা আবশ্যক'),
])
def test_real_roles_are_retained(title, description):
    assert assess(title, description).relevant


def test_company_prefix_does_not_count_as_cyber_keyword():
    assert not strong_terms('CyberArk, CyberSource and Cyberdyne')
    assert strong_terms('Cybersecurity, Cyber Security and Cyber-Defense')


@pytest.mark.parametrize(('url', 'expected'), [
    ('https://www.linkedin.com/jobs/view/4012345678/', True),
    ('https://bd.linkedin.com/jobs/view/security-engineer-at-bank-4012345678?trk=x', True),
    ('https://www.linkedin.com/jobs/search/?keywords=SOC', False),
    ('https://www.linkedin.com/posts/security-engineer-4012345678', False),
    ('https://linkedin.com.evil.example/jobs/view/4012345678/', False),
    ('https://jobs.bdjobs.com/jobdetails.asp?id=1234567', True),
    ('https://jobs.bdjobs.com/jobsearch.asp?txtKeyword=security', False),
    ('https://bdjobs.com.evil.example/jobdetails.asp?id=1234567', False),
])
def test_portal_job_url_requires_exact_host_and_individual_route(url, expected):
    assert is_portal_job_url(url) is expected


def test_title_and_careers_url_alone_do_not_prove_vacancy():
    result = assess_vacancy('Information Security Analyst',
                            'Information Security Analyst is a popular occupation. Our careers guide explains the profession.' * 3,
                            'https://bank.example/careers/security-analyst')
    assert not result.vacancy
    assert 'insufficient' in result.reason


def test_role_specific_registration_is_rejected_even_on_job_path():
    result = assess_vacancy('SOC Analyst',
                            'Register now for a SOC Analyst workshop in Dhaka. Registration fee BDT 500.',
                            'https://bank.example/careers/soc-analyst')
    assert not result.vacancy
    assert 'registration' in result.reason


@pytest.mark.parametrize(('title', 'desc', 'url', 'kind'), [
    ('SOC Analyst', 'Qualifications: two years. Responsibilities: monitor SIEM. Apply now.', 'https://bank.example/careers/soc-analyst', 'html'),
    ('Senior Information Security Officer', 'Recruitment circular: please submit applications by the deadline.', 'https://bank.example/files/circular.pdf', 'pdf'),
    ('SOC Analyst', '', 'https://www.linkedin.com/jobs/view/4012345678', 'alert'),
    ('Information Security Engineer', 'A Bangladesh-based role.', 'https://bd.linkedin.com/jobs/view/security-engineer-111', 'index'),
    ('Information Security Specialist', 'Information security monitoring and ISO 27001.', 'https://bank.example/careers/infosec-specialist', 'official_rss'),
    ('Security Engineer', 'Detect attacks.', 'https://ats.example/123', 'ats'),
    ('Security Engineer', '', 'https://publisher.example/123', 'publisher'),
    ('তথ্য নিরাপত্তা কর্মকর্তা নিয়োগ', 'যোগ্যতা: স্নাতক। আবেদনের শেষ তারিখ: ৩০ ডিসেম্বর।', 'https://bank.example/careers/1', 'html'),
])
def test_valid_vacancy_evidence_retains_sparse_and_bilingual_sources(title, desc, url, kind):
    outcome = assess_vacancy(title, desc, url, source_kind=kind)
    assert outcome.vacancy
    assert outcome.score >= 70
    assert outcome.reason and outcome.signals


def test_news_page_can_carry_an_actual_job_circular():
    outcome = assess_vacancy('City Bank hiring Information Security Officer',
                            'Job circular in Dhaka. Qualifications: CSE degree. Apply by 30 November 2026.',
                            'https://news.example/bank-security-circular', source_kind='feed')
    assert outcome.vacancy


def test_application_keyword_is_not_enough_for_event_feed():
    outcome = assess_vacancy('Information Security',
                            'Application for a cybersecurity course. Job-ready training in Bangladesh.',
                            'https://academy.example/course/info-security', source_kind='feed')
    assert not outcome.vacancy


@pytest.mark.parametrize('title', [
    'Threat Hunter', 'Incident Handler', 'Red Team Operator', 'Cybercrime Investigator',
    'Ethical Hacker', 'Cryptographer', 'Privacy Counsel',
])
def test_less_common_security_occupations_survive_sparse_portal_snippets(title):
    assert assess(title).relevant
    assert assess_vacancy(title, '', 'https://www.linkedin.com/jobs/view/4012345678', source_kind='index').vacancy


def test_legacy_validation_preserves_record_and_recognises_ats_metadata():
    record = {'title': 'Security Engineer', 'description': 'Detect attacks.',
              'verification_level': 'Published ATS API', 'source_url': 'https://ats.example/1',
              'posted_at': '2026-01-20', 'source': 'Greenhouse public API'}
    original = copy.deepcopy(record)
    assert assess_record(record).vacancy
    assert record == original


def test_legacy_event_is_rejected_despite_prior_high_score():
    record = {'title': 'SOC Analyst Training', 'description': 'Apply now for our bootcamp.',
              'source_url': 'https://bank.example/careers/soc', 'verification_level': 'Official page parsed',
              'relevance_score': 98}
    outcome = assess_record(record)
    assert not outcome.vacancy
    assert 'training' in outcome.reason


def test_legacy_seed_corpus_keeps_verified_job_leads():
    root = Path(__file__).resolve().parents[1]
    rows = json.loads((root / 'tests/fixtures/seed_jobs.json').read_text())['jobs']
    rejected = [(row['title'], assess_record(row).reason) for row in rows if not assess_record(row).vacancy]
    assert rejected == []


@pytest.mark.parametrize('fragment', [
    'Reports to Chief Information Security Officer',
    'Reporting to SOC Manager',
    'Work closely with the SOC Analyst',
    'For enquiries contact the Information Security Officer',
    'Hiring Manager: Information Security Officer',
    'Experience as a Security Engineer is required',
    'The Information Security Officer will monitor SIEM alerts',
    'দায়িত্ব: তথ্য নিরাপত্তা কর্মকর্তার সাথে যোগাযোগ',
])
def test_pdf_contact_and_duty_lines_do_not_create_extra_vacancies(fragment):
    assert not assess(fragment).relevant
    assert not assess_vacancy(fragment,
        'Recruitment circular. We are hiring. Qualifications: CSE. Apply now.',
        'https://bank.example/files/circular.pdf', source_kind='pdf').vacancy


def test_pdf_multiple_roles_are_kept_without_reporting_line_false_positives(monkeypatch):
    import pypdf
    from collector import collect as c
    class Page:
        def extract_text(self):
            return ('Recruitment circular. Please submit applications.\n'
                    'Information Security Officer\nSOC Analyst\n'
                    'Reports to Chief Information Security Officer\n'
                    'Work closely with the SOC Analyst\n')
    class Reader:
        def __init__(self, *args, **kwargs): self.pages = [Page()]
    monkeypatch.setattr(pypdf, 'PdfReader', Reader)
    records = c.parse_pdf_circular(b'%PDF-test', 'https://bank.example/files/circular.pdf', 'Bank', [])
    assert {r['title'] for r in records} == {'Information Security Officer', 'SOC Analyst'}
    assert len(c.deduplicate(records)) == 2


def test_official_html_generic_bank_title_uses_department_evidence():
    from collector import collect as c
    html = '''<html><main><h1>Senior Principal Officer</h1>
      <p>Place of posting: Information Security Division. Responsibilities: monitor SIEM and
      perform penetration testing. Qualifications: university degree.
      Apply now via the recruitment portal.</p></main></html>'''
    jobs = c.scrape_official_job(html, 'https://bank.example/careers/spo', [], 'Example Bank')
    assert len(jobs) == 1 and jobs[0]['title'] == 'Senior Principal Officer'


@pytest.mark.parametrize('location', ['Remote - US only', 'United Arab Emirates', 'Ireland'])
def test_explicit_foreign_location_overrides_incidental_country_mentions(location):
    from collector import collect as c
    region = c.classify_region(location, 'We serve businesses in Bangladesh and around the world.', remote=True)
    assert region is None


def test_structured_remote_applicant_restriction_is_not_defaulted_to_bangladesh():
    from collector import collect as c
    node = {'@type': 'JobPosting', 'title': 'Security Engineer', 'description': 'Detect threats.',
            'jobLocationType': 'TELECOMMUTE',
            'applicantLocationRequirements': {'@type': 'Country', 'name': 'United States'}}
    html = '<script type="application/ld+json">' + json.dumps(node) + '</script>'
    assert not c.scrape_official_job(html, 'https://bank.example/careers/1', [], 'Example Bank')


def test_structured_multiple_locations_retains_bangladesh_option():
    from collector import collect as c
    node = {'@type': 'JobPosting', 'title': 'Security Engineer', 'description': 'Detect threats.',
            'jobLocation': [{'address': {'addressCountry': 'India'}},
                            {'address': {'addressCountry': 'Bangladesh'}}]}
    html = '<script type="application/ld+json">' + json.dumps(node) + '</script>'
    jobs = c.scrape_official_job(html, 'https://bank.example/careers/1', [], 'Example Bank')
    assert len(jobs) == 1
    assert jobs[0]['region'] == 'Bangladesh' and 'Bangladesh' in jobs[0]['location']


def test_structured_listing_without_individual_urls_preserves_distinct_roles():
    from collector import collect as c
    nodes = [{'@type': 'JobPosting', 'title': title,
              'description': 'Full-time. Responsibilities: monitor SIEM. Qualifications: CSE. Apply now.',
              'jobLocation': {'address': {'addressCountry': 'Bangladesh'}}}
             for title in ('SOC Analyst', 'Information Security Officer')]
    html = '<script type="application/ld+json">' + json.dumps(nodes) + '</script>'
    jobs = c.scrape_official_job(html, 'https://bank.example/careers', [], 'Example Bank')
    assert len(c.deduplicate(jobs)) == 2
    assert len({job['id'] for job in jobs}) == 2
