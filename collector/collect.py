"""CyberCareers BD hourly, API-key-free cyber job collection.

Uses public free provider feeds, official employer pages and published ATS endpoints.
Respects robots, paywalls, request limits and explicit geographic eligibility.
Third-party commercial job portals including LinkedIn are searchable as source links
but are not directly scraped or bypassed.
"""
from __future__ import annotations

import argparse
import hashlib
import io
import html
import ipaddress
import json
import logging
import os
import re
import time
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urljoin, urlparse, urlunparse, parse_qs, urlencode
from urllib.robotparser import RobotFileParser

import requests
import threading
import unicodedata
from concurrent.futures import ThreadPoolExecutor, as_completed
from bs4 import BeautifulSoup

from . import relevance as _relevance
from .vacancy import assess_vacancy, assess_record, source_kind_for_record, has_role_title, is_job_detail_url
from . import textmine
from .robots import ALLOW_ALL, RobotsPolicy
from .telemetry import source_started

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / 'data'
UA = 'CyberCareersBD/5.2 (+personal public vacancy watch; honours robots.txt)'
BANGLADESH = timezone(timedelta(hours=6))
# Search portal URLs are kept in the source directory; no paid API is used.
HTTP_TIMEOUT = 12
KEYWORDS = [
    'cybersecurity','cyber security','cyber-security','cyber defense','infrastructure security','information security',
    'it security','application security','appsec','api security','mobile security',
    'penetration test','pentester','red team','blue team','security engineer',
    'soc analyst','cyber threat','threat intelligence','threat hunting','siem',
    'devsecops','cloud security','cloud security architect','security governance',
    'security risk','security compliance','grc','isms','it audit','security audit',
    'ciso','chief information security','security operations','iam engineer',
    'identity and access management','security architect','digital forensics',
    'vulnerability management','vapt','secure coding','ai security','llm security',
    'security analyst','incident responder','network & security','network and security','security administrator',
    'risk and compliance','privacy engineer','ot security','incident response',
    'infosec','information assurance','information systems security','infosecurity',
    'security assurance','security control','cyber risk','technology risk','ict risk',
    'it governance','third party risk','vendor risk','security monitoring',
    'it compliance','technology audit','it auditor','information systems audit',
    'ict security','security assessment','security testing','security analyst',
    'security specialist','security consultant','security advisory','security researcher',
    'security researcher','data security','database security','endpoint security',
    'iam specialist','soc engineer','soc manager','soc lead','security operations center',
    'cybersecurity engineer','security devops','security automation','product security',
    'platform security','enterprise security','data privacy','privacy officer',
    'computer security incident response','cert analyst','csirt','dfir',
    'malware analysis','malware analyst','reverse engineer','ransomware response',
    'vulnerability researcher','offensive security','ethical hacker',
    'compliance analyst','business continuity','disaster recovery','swift security',
    'cyber resilience','cloud security posture','security engineer',
    'business information security', 'biso', 'it risk management', 'it risk analyst',
    'information security officer', 'information security analyst', 'information security engineer',
    'information security manager', 'security analyst', 'product security', 'platform security',
    'security program manager', 'cyber defence', 'cyber defense', 'cyber risk analyst',
    'security assurance', 'digital risk', 'financial crime technology', 'fraud technology security',
    'security data engineer', 'data privacy officer', 'security operations engineer',
    'application penetration tester', 'information systems auditor', 'technology controls',
    'threat researcher', 'offensive security engineer', 'security testing engineer',
    'identity security', 'ot cybersecurity', 'industrial cybersecurity', 'cyber resilience',
    'information technology risk', 'cyber fraud detection', 'security vulnerability analyst',
    'soc l1', 'soc l2', 'soc l3', 'security automation engineer', 'cybersecurity consultant',
    # Bengali / Bangla forms used in career announcements, titles and PDFs.
    'সাইবার নিরাপত্তা', 'সাইবার সিকিউরিটি', 'সাইবার সুরক্ষা', 'সাইবার ডিফেন্স',
    'তথ্য নিরাপত্তা', 'তথ্য সুরক্ষা', 'ইনফরমেশন সিকিউরিটি',
    'আইটি সিকিউরিটি', 'আইসিটি সিকিউরিটি', 'অ্যাপ্লিকেশন সিকিউরিটি',
    'অ্যাপ্লিকেশন নিরাপত্তা', 'নেটওয়ার্ক নিরাপত্তা', 'নেটওয়ার্ক নিরাপত্তা',
    'পেনিট্রেশন টেস্টিং', 'পেনেট্রেশন টেস্টিং', 'পেন্টেস্ট', 'ভিএপিটি',
    'ভালনারেবিলিটি অ্যাসেসমেন্ট', 'ভালনারেবিলিটি ম্যানেজমেন্ট',
    'সিকিউরিটি অপারেশনস সেন্টার', 'সাইবার থ্রেট', 'তথ্যপ্রযুক্তি নিরীক্ষা',
    'আইটি অডিট', 'সিকিউরিটি অডিট', 'আইটি ঝুঁকি', 'সাইবার ঝুঁকি',
    'ডিজিটাল ফরেনসিক', 'সাইবার গোয়েন্দা', 'সাইবার গোয়েন্দা',
    'নিরাপত্তা প্রকৌশলী', 'নিরাপত্তা বিশ্লেষক',
]
BLOCKED_TITLE = re.compile(r'\b(security guard|security officer.*(?:guard|premises)|security supervisor.*physical|safety officer|armed guard|security camera|physical security|security agent.*airport|security personnel|guard commander)\b', re.I)
BANGLA_SEARCH_TERMS = [
    'সাইবার নিরাপত্তা নিয়োগ', 'সাইবার সিকিউরিটি চাকরি', 'তথ্য নিরাপত্তা কর্মকর্তা নিয়োগ',
    'তথ্য নিরাপত্তা বিভাগ ব্যাংক চাকরি', 'ইনফরমেশন সিকিউরিটি অফিসার',
    'আইটি সিকিউরিটি ব্যাংক নিয়োগ', 'সাইবার থ্রেট ইন্টেলিজেন্স চাকরি',
    'নেটওয়ার্ক নিরাপত্তা প্রকৌশলী নিয়োগ', 'অ্যাপ্লিকেশন সিকিউরিটি চাকরি',
    'সিকিউরিটি অপারেশনস সেন্টার নিয়োগ', 'তথ্যপ্রযুক্তি নিরীক্ষা ব্যাংক নিয়োগ',
    'সাইবার নিরাপত্তা ব্যবস্থাপক চাকরি',
]
BANGLA_JOB_WORDS = r'(?:চাকরি|নিয়োগ|নিয়োগ|ক্যারিয়ার|ক্যারিয়ার|পদে|শূন্যপদ|বিজ্ঞপ্তি|সার্কুলার)'
BANGLA_SECURITY_OFFICE = r'(?:কর্মকর্তা|প্রকৌশলী|বিশ্লেষক|ব্যবস্থাপক|পরামর্শক|প্রধান|অফিসার|অডিটর|বিশেষজ্ঞ)'
SUSPICIOUS_CONTENT = re.compile(r'(captcha|access denied|please enable javascript|too many requests)', re.I)



def now_bd() -> datetime:
    return datetime.now(BANGLADESH)


def today_iso() -> str:
    return now_bd().date().isoformat()


def get_json(path: Path, default: Any) -> Any:
    try:
        return json.loads(path.read_text(encoding='utf-8'))
    except (FileNotFoundError, json.JSONDecodeError):
        return default


def write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix('.tmp')
    temporary.write_text(json.dumps(data, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    temporary.replace(path)


def clean_text(value: Any, maxlen=15000) -> str:
    if value is None:
        return ''
    if isinstance(value, (list, dict)):
        value = str(value)
    value = str(value)
    if '<' in value and '>' in value:
        value = BeautifulSoup(value, 'html.parser').get_text(' ', strip=True)
    value = unicodedata.normalize('NFKC', html.unescape(value))
    value = value.replace('\u200b', '').replace('\u200c', '').replace('\u200d', '')
    return re.sub(r'\s+', ' ', value).strip()[:maxlen]


def valid_url(value: str) -> bool:
    try:
        u = urlparse(value)
        if u.scheme not in ('http', 'https') or not u.hostname:
            return False
        if u.port is not None and not 1 <= u.port <= 65535:
            return False
        host = u.hostname.strip('.').lower()
        if host in ('localhost',) or host.endswith(('.local', '.internal', '.test')):
            return False
        try:
            ipaddress.ip_address(host)
            return False
        except ValueError:
            pass
        if len(value) > 2000 or '@' in u.netloc:
            return False
        return True
    except (ValueError, TypeError):
        return False


def same_host_or_subdomain(host: str, domain: str) -> bool:
    host = (host or '').lower()
    domain = (domain or '').lower()
    if domain.startswith('www.'): domain=domain[4:]
    return bool(host and domain and (host == domain or host.endswith('.' + domain)))


def is_relevant(title: str, description: str = '') -> bool:
    """Weighted bilingual relevance (see collector/relevance.py)."""
    return _relevance.assess(clean_text(title, 300), clean_text(description, 12000)).relevant


_CATEGORY_RULES = [
    ('AI & LLM Security', r'\b(?:llm|ai security|ml security|model security|artificial intelligence security|ai red team)'),
    ('Security Leadership', r'\b(?:ciso|biso|chief information security|head of (?:information |cyber ?)?security|security director|director,? (?:information |cyber ?)?security|vp,? security)\b|নিরাপত্তা প্রধান'),
    ('Application Security', r'\b(?:penetration|pen ?test|red team|offensive|vapt|ethical hack|bug bounty|appsec|application security|api security|mobile (?:app )?security|product security|secure cod)|অ্যাপ্লিকেশন|পেনিট্রেশন|পেনেট্রেশন|ভিএপিটি'),
    ('SOC & Threat Detection', r'\b(?:soc|siem|soar|edr|xdr|cyber defen[cs]e|threat|incident respon|dfir|forensic|malware|detection|security operations|security monitoring|blue team|csirt)\b|সাইবার থ্রেট|অপারেশনস সেন্টার'),
    ('Network & Cloud Security', r'\b(?:cloud|network|firewall|waf|devsecops|infrastructure security|endpoint|zero trust|sase|iam|identity|privileged access|pam)\b|নেটওয়ার্ক|নেটওয়ার্ক'),
    ('GRC & Security Operations', r'\b(?:audit|governance|risk|compliance|isms|grc|iso ?27001|pci|privacy|assurance|controls?)\b|নিরীক্ষা|ঝুঁকি|অডিট'),
]


def categorize(title: str) -> str:
    t = clean_text(title, 300).lower()
    for label, pattern in _CATEGORY_RULES:
        if re.search(pattern, t, re.I):
            return label
    return 'General Cybersecurity'


SKILL_PATTERNS: dict[str, str] = {
    'Web Security':r'\bweb (?:application )?security\b|\bowasp top 10\b',
    'API Security':r'\bapi security\b|\bowasp api\b',
    'Mobile Security':r'\bmobile (?:app(?:lication)? )?security\b',
    'LLM Security':r'\bllm\b|\bprompt injection\b',
    'AI Security':r'\bai security\b|\bmodel security\b|\badversarial ai\b',
    'Penetration Testing':r'\bpenetration test|\bpen[ -]?test|\bvapt\b',
    'Burp Suite':r'\bburp\b',
    'OWASP':r'\bowasp\b',
    'Vulnerability Assessment':r'\bvulnerability (?:assessment|management|scan)|\bnessus\b|\bopenvas\b',
    'SIEM':r'\bsiem\b|\bsplunk\b|\bsentinel\b',
    'SOAR':r'\bsoar\b',
    'SOC':r'\bsoc\b|\bsecurity operations cent',
    'EDR':r'\bedr\b|\bxdr\b',
    'Incident Response':r'\bincident response\b|\bincident handling\b',
    'Threat Detection':r'\bthreat detection\b|\bthreat hunting\b',
    'Cyber Threat Intelligence':r'\bthreat intelligence\b|\bcti\b',
    'Network Security':r'\bnetwork security\b|\bfirewall\b|\bids/ips\b',
    'Cloud Security':r'\bcloud security\b|\bcloud security posture\b',
    'AWS':r'\baws\b|\bamazon web services\b',
    'Azure':r'\bazure\b',
    'GCP':r'\bgcp\b|\bgoogle cloud\b',
    'DevSecOps':r'\bdevsecops\b|\bsecure cicd\b|\bsecure ci/cd\b',
    'SAST':r'\bsast\b|\bstatic application security\b',
    'DAST':r'\bdast\b|\bdynamic application security\b',
    'Secure Code Review':r'\bsecure code review\b|\bsecurity code review\b',
    'Threat Modeling':r'\bthreat model\b',
    'IAM':r'\biam\b|\bidentity and access\b|\bidentity management\b',
    'PAM':r'\bpam\b|\bprivileged access\b',
    'DLP':r'\bdlp\b|\bdata loss prevention\b',
    'ISO 27001':r'\biso[ /-]?27001\b',
    'PCI DSS':r'\bpci[ -]?dss\b',
    'NIST':r'\bnist\b',
    'Security Governance':r'\bsecurity governance\b|\bsecurity policy\b',
    'Risk Management':r'\brisk management\b|\brisk assessment\b',
    'Security Reporting':r'\bsecurity reporting\b|\bdashboard\b|\bexecutive reporting\b',
    'ISMS':r'\bisms\b|\binformation security management system\b',
    'Python':r'\bpython\b',
    'Linux':r'\blinux\b',
    'Information Security':r'\binformation security\b|\binfosec\b',
    'Security Operations':r'\bsecurity operations\b',
    'Incident Management':r'\bincident management\b',
    'Compliance':r'\bcompliance\b',
    'SWIFT CSP':r'\bswift\s*(?:csp|cscf)\b',
    'Black Duck':r'\bblack duck\b|\bblackduck\b',
    'Coverity':r'\bcoverity\b',
    'Tenable':r'\btenable\b',
    'Nessus':r'\bnessus\b',
    'QRadar':r'\bqradar\b',
    'F5 WAF':r'\bf5\b|\bweb application firewall\b|\bwaf\b',
    'ISO 27001 Audit':r'\binternal (?:security )?audit\b',
    'Fortinet':r'\bfortinet\b|\bfortigate\b',
    'Cisco':r'\bcisco\b|\bccna\b',
    'Terraform':r'\bterraform\b',
    'Docker':r'\bdocker\b',
}


# Bilingual requirements and tool names map to the existing match-score labels.
SKILL_PATTERNS.update({
    'Information Security': SKILL_PATTERNS['Information Security'] + r'|তথ্য নিরাপত্তা|তথ্য সুরক্ষা|ইনফরমেশন সিকিউরিটি',
    'Penetration Testing': SKILL_PATTERNS['Penetration Testing'] + r'|পেনিট্রেশন টেস্টিং|পেনেট্রেশন টেস্টিং|পেন্টেস্ট|ভিএপিটি',
    'API Security': SKILL_PATTERNS['API Security'] + r'|এপিআই সিকিউরিটি|এপিআই নিরাপত্তা',
    'Network Security': SKILL_PATTERNS['Network Security'] + r'|নেটওয়ার্ক নিরাপত্তা|নেটওয়ার্ক নিরাপত্তা',
    'SOC': SKILL_PATTERNS['SOC'] + r'|সিকিউরিটি অপারেশনস সেন্টার',
    'Security Governance': SKILL_PATTERNS['Security Governance'] + r'|নিরাপত্তা নীতিমালা|তথ্য নিরাপত্তা নীতি',
    'Vulnerability Assessment': SKILL_PATTERNS['Vulnerability Assessment'] + r'|ভালনারেবিলিটি অ্যাসেসমেন্ট|ভালনারেবিলিটি ম্যানেজমেন্ট',
    'Cyber Threat Intelligence': SKILL_PATTERNS['Cyber Threat Intelligence'] + r'|সাইবার থ্রেট ইন্টেলিজেন্স|সাইবার গোয়েন্দা',
})


def find_skills(text: str) -> list[str]:
    return [s for s, pattern in SKILL_PATTERNS.items() if re.search(pattern, text, re.I)]


def iso_date(raw: Any) -> str:
    if not raw: return ''
    text = str(raw).strip()
    try:
        return datetime.fromisoformat(text.replace('Z', '+00:00')).date().isoformat()
    except ValueError:
        pass
    for fmt in ('%d %b %Y','%d %B %Y','%b %d, %Y','%B %d, %Y','%d/%m/%Y','%Y/%m/%d'):
        try: return datetime.strptime(text[:40],fmt).date().isoformat()
        except ValueError: pass
    return textmine.parse_date(text[:60])


def deadline_date(raw: Any) -> str:
    """A valid application-deadline day in Bangladesh, or '' when unknown.

    Date-only circulars keep their stated calendar day.  Timestamp deadlines
    are first converted to BDT; the dashboard then treats that day as open
    through its end.  This intentionally leaves publication-date semantics
    in ``iso_date`` unchanged and does not claim exact closing-hour accuracy.
    """
    if not raw or isinstance(raw, (bool, dict, list, tuple, set)):
        return ''
    text = str(raw).strip()
    if re.fullmatch(r'\d{10,13}(?:\.\d+)?', text):
        try:
            seconds = float(text)
            if seconds > 1e11:
                seconds /= 1000
            return datetime.fromtimestamp(seconds, BANGLADESH).date().isoformat()
        except (ValueError, OverflowError, OSError):
            return ''
    try:
        parsed = datetime.fromisoformat(text.replace('Z', '+00:00'))
        if parsed.tzinfo is not None:
            parsed = parsed.astimezone(BANGLADESH)
        return parsed.date().isoformat()
    except ValueError:
        # A broken ISO timestamp must not fall through to a parser that finds
        # just its plausible date prefix and silently discards the bad time.
        if re.match(r'^\d{4}-\d{2}-\d{2}[Tt ]', text):
            return ''
    return iso_date(raw)


def years_from_text(text: str) -> int | None:
    return textmine.years_required(text)


def stable_id(company: str, title: str, url: str) -> str:
    # Use semantic identity for duplicates on different job boards.
    def norm(s):
        s = s.lower().replace('limited','').replace('ltd.','').replace('plc','')
        return re.sub(r'[^a-z0-9]+',' ',s).strip()
    # Different requisition URLs may genuinely contain different positions
    # with identical job titles. Keep both instead of collapsing by title.
    canonical = canonical_job_url(url) if valid_url(url) else ''
    seed = canonical or (norm(company) + '|' + norm(title))
    if canonical and urlparse(canonical).path.lower().endswith('.pdf'):
        seed += '|' + _norm_title(title)
    return hashlib.sha256(seed.encode()).hexdigest()[:18]


def canonical_job_url(url: str) -> str:
    if not valid_url(url):
        return ''
    from .email_alerts import canonical_portal_job
    portal = canonical_portal_job(url)
    if portal:
        return portal[1].rstrip('/')
    u = urlparse(url)
    query = parse_qs(u.query, keep_blank_values=False)
    # Keep job identifiers; strip common link click tracking only.
    query = {k: v for k, v in query.items() if not k.lower().startswith(('utm_', 'fbclid', 'gclid'))
             and k.lower() not in ('referrer', 'trk', 'tracking')}
    host = (u.hostname or '').lower()
    if u.port and u.port not in (80, 443):
        host += ':' + str(u.port)
    return urlunparse((u.scheme.lower(), host,
        u.path.rstrip('/') or '/', '', urlencode(sorted((k, val) for k, values in query.items() for val in values)), ''))


def derive_sector(company: str, sources: list[dict]) -> str:
    c = company.lower().replace(' limited','').replace(' ltd','').replace(' plc','').strip()
    for source in sources:
        name = source['name'].lower().replace(' limited','').replace(' ltd','').replace(' plc','').strip()
        if c == name or (len(c)>7 and (c in name or name in c)):
            return source['sector']
    return 'Other'


def job_source_attribution(source: str, company: str, url: str) -> dict[str, str]:
    """Preserve where a listing came from, independent of its apply destination.

    `source` is the collection platform/method (backwards compatible), while
    `source_name` and `source_domain` identify the publisher shown to users.
    These fields are never inferred from the application URL when a separate
    original listing URL was supplied.
    """
    domain = (urlparse(url).hostname or '').lower().removeprefix('www.') if valid_url(url) else ''
    publisher = {
        'LinkedIn index': 'LinkedIn', 'Bdjobs index': 'Bdjobs',
        'Indeed index': 'Indeed', 'Glassdoor index': 'Glassdoor',
        'Dohaj index': 'Dohaj', 'Job Lagbe index': 'Job Lagbe',
        'Himalayas': 'Himalayas', 'Jobicy': 'Jobicy',
        'Remotive': 'Remotive', 'Remote OK': 'Remote OK',
    }.get(source)
    if not publisher and source.startswith('Official PDF'):
        publisher = f'{company} · recruitment circular'
    elif not publisher and source.startswith('Official employer RSS'):
        publisher = f'{company} · official jobs RSS'
    elif not publisher and source.startswith('Official employer'):
        publisher = f'{company} · official careers'
    elif not publisher and source.endswith(' public API'):
        publisher = source.replace(' public API', '') + f' · {company}'
    return {'source_name': publisher or source or domain or 'Original job posting',
            'source_domain': domain}


def new_job(*, title: str, company: str, url: str, source: str, sources: list[dict], description: str='', posted: str='', deadline: str='', skills: list[str] | None=None, **kwargs) -> dict:
    description=clean_text(description,11000)
    title=clean_text(title,200)
    company=clean_text(company,150)
    # Many circulars only state the deadline/posted date in body text (incl. Bangla).
    if not deadline_date(deadline):
        deadline=textmine.find_deadline(description)
    if not iso_date(posted):
        posted=textmine.find_posted(description[:4000])
    if kwargs.get('location') in (None,'','Bangladesh (verify location)'):
        city=textmine.bd_city(title+' '+description[:1500]) if kwargs.get('region','Bangladesh')=='Bangladesh' else ''
        if city:kwargs['location']=f'{city}, Bangladesh'
    assessed=_relevance.assess(title,description)
    evidence=assess_vacancy(title,description,url,source_kind=source_kind_for_record(
        {'source':source,'verification_level':kwargs.get('verification_level','')}))
    identifier=stable_id(company,title,url)
    if kwargs.get('posting_identifier') or kwargs.get('shared_listing_url') or source.startswith('Official PDF'):
        discriminator=str(kwargs.get('posting_identifier') or _norm_title(title))
        identifier=hashlib.sha256((identifier+'|'+discriminator).encode()).hexdigest()[:18]
    return {
        'id':identifier+('-intl' if kwargs.get('region')=='International' else ''), 'title':title, 'company':company or 'Employer not identified',
        'company_sector':kwargs.get('company_sector') or derive_sector(company,sources),
        'location':kwargs.get('location') or 'Bangladesh (verify location)',
        'workplace':kwargs.get('workplace') or 'Not specified',
        'employment_type':kwargs.get('employment_type') or 'Not specified',
        'seniority':kwargs.get('seniority') or 'Not specified', 'category':categorize(title),
        'posted_at':iso_date(posted), 'deadline':deadline_date(deadline),
        'min_years':kwargs.get('min_years',years_from_text(description)), 'max_years':None,
        'salary':kwargs.get('salary') or 'Not disclosed',
        'skills':skills if skills is not None else find_skills(title+' '+description),
        'description':description[:11000], 'responsibilities':kwargs.get('responsibilities') or [],
        'requirements':kwargs.get('requirements') or [],
        'source':source, 'source_url':url, 'apply_url':kwargs.get('apply_url') or url,
        'source_name':kwargs.get('source_name') or job_source_attribution(source,company,url)['source_name'],
        'source_domain':kwargs.get('source_domain') or job_source_attribution(source,company,url)['source_domain'],
        'company_logo_url':kwargs.get('company_logo_url') or '', 'poster_url':kwargs.get('poster_url') or '',
        'verification_level':kwargs.get('verification_level') or 'Search indexed',
        'description_status':kwargs.get('description_status') or 'Search excerpt',
        'region': kwargs.get('region') or 'Bangladesh',
        'eligibility': kwargs.get('eligibility') or 'Bangladesh role — verify requirements',
        'eligibility_confidence': kwargs.get('eligibility_confidence') or ('unconfirmed' if kwargs.get('region')=='International' else 'local'),
        'vacancy_status': kwargs.get('vacancy_status') or 'unverified',
        'relevance_score': assessed.score, 'matched_terms': assessed.terms[:12],
        'relevance_reason': assessed.reason,
        'vacancy_score': evidence.score, 'vacancy_reason': evidence.reason,
        'vacancy_evidence': evidence.signals, 'detection_version': '5.2',
        'alert_received_at': kwargs.get('alert_received_at') or '',
        'provider_updated_at': kwargs.get('provider_updated_at') or '',
        'source_updated_at': kwargs.get('source_updated_at') or '',
        'posting_identifier': kwargs.get('posting_identifier') or '',
        'shared_listing_url': bool(kwargs.get('shared_listing_url')),
        'also_listed_on': kwargs.get('also_listed_on') or [],
        'collected_at':today_iso(), 'last_seen_at':today_iso(),
        'last_observed_at':now_bd().isoformat(timespec='seconds')
    }


def jobposting_nodes(data: Any):
    if isinstance(data, list):
        for x in data: yield from jobposting_nodes(x)
    if isinstance(data, dict):
        typ=data.get('@type',[])
        if isinstance(typ,str): typ=[typ]
        if any(str(t).lower().endswith('jobposting') for t in typ): yield data
        for nested in ('@graph','mainEntity','itemListElement'):
            if nested in data: yield from jobposting_nodes(data[nested])


def _microdata(element) -> dict:
    out: dict[str, Any] = {}
    for prop in element.select('[itemprop]'):
        # Only direct properties of this item, not of nested items.
        parent = prop.find_parent(attrs={'itemscope': True})
        if parent is not element:
            continue
        key = prop.get('itemprop')
        if prop.has_attr('itemscope'):
            value: Any = _microdata(prop)
        else:
            value = prop.get('content') or prop.get('datetime') or prop.get('href') or prop.get_text(' ', strip=True)
        out.setdefault(key, value)
    return out


def get_ld(soup: BeautifulSoup) -> list[dict]:
    """schema.org JobPosting from JSON-LD and from HTML microdata."""
    found=[]
    for script in soup.select('script[type="application/ld+json"]'):
        raw=(script.string or script.get_text() or '').strip()
        # Some CMSs emit trailing commas or HTML comments inside JSON-LD.
        raw=re.sub(r'^\s*<!--|-->\s*$','',raw)
        raw=re.sub(r',\s*([}\]])',r'\1',raw)
        try:
            data=json.loads(raw, strict=False)
            found.extend(jobposting_nodes(data))
        except (ValueError,TypeError): pass
    for item in soup.select('[itemscope][itemtype*="JobPosting" i]')[:30]:
        data=_microdata(item)
        if data.get('title'):
            data['@type']='JobPosting'
            found.append(data)
    return found


def value_of(obj: Any) -> str:
    if isinstance(obj,str): return obj
    if isinstance(obj,dict): return str(obj.get('name') or obj.get('value') or '')
    if isinstance(obj,list): return ', '.join(filter(None,(value_of(x) for x in obj)))
    return ''


def extract_role_sections(soup: BeautifulSoup) -> tuple[list[str], list[str]]:
    """Read explicit requirements and responsibilities from public vacancy HTML.

    Only extracts text that the employer actually published, with a small
    output budget. No attempt to infer requirements from unrelated page text.
    """
    groups: dict[str, list[str]] = {'requirements': [], 'responsibilities': []}
    patterns = {
        'requirements': re.compile(r'\b(requirements?|qualifications?|eligibility|education|experience required|what you bring)\b|যোগ্যতা|অভিজ্ঞতা|শিক্ষাগত', re.I),
        'responsibilities': re.compile(r'\b(responsibilit(?:y|ies)|duties|what you\W*ll do|key tasks|role overview)\b|দায়িত্ব|দায়িত্ব|কর্তব্য', re.I),
    }
    for heading in soup.select('h2, h3, h4, h5')[:55]:
        label = clean_text(heading.get_text(' ', strip=True), 180)
        category = next((k for k, p in patterns.items() if p.search(label)), '')
        if not category:
            continue
        sibling = heading.next_sibling
        examined = 0
        while sibling and examined < 6 and len(groups[category]) < 18:
            examined += 1
            if getattr(sibling, 'name', None) in ('h2', 'h3', 'h4', 'h5'):
                break
            if getattr(sibling, 'select', None):
                bullets = sibling.select('li')[:18]
                if bullets:
                    texts = [clean_text(li.get_text(' ', strip=True), 500) for li in bullets]
                else:
                    content = clean_text(sibling.get_text(' ', strip=True), 950)
                    texts = [content] if content else []
                for text in texts:
                    if len(text) >= 12 and text not in groups[category]:
                        groups[category].append(text)
            sibling = sibling.next_sibling
    return groups['requirements'], groups['responsibilities']


def scrape_official_job(htmltext: str, page_url: str, sources: list[dict], company_hint: str='') -> list[dict]:
    """Parse compliant employer job pages; prioritize structured JobPosting JSON-LD."""
    soup=BeautifulSoup(htmltext,'lxml')
    jobs=[]
    for node in get_ld(soup):
        title=clean_text(node.get('title'),200)
        desc=clean_text(node.get('description'),11000)
        if not is_relevant(title,desc) or not assess_vacancy(title,desc,page_url,source_kind='jobposting').vacancy: continue
        employer=node.get('hiringOrganization',{})
        company=value_of(employer) or company_hint
        def location_text(item):
            if isinstance(item, list):
                return '; '.join(filter(None, (location_text(x) for x in item)))
            if isinstance(item, dict):
                addr=item.get('address', item)
                if isinstance(addr, dict):
                    parts=[value_of(addr[k]) for k in ('addressLocality','addressRegion','addressCountry') if addr.get(k)]
                    return ', '.join(filter(None,parts)) or value_of(item)
                return value_of(addr)
            return value_of(item)
        places=[location_text(x) for x in (node.get('jobLocation') if isinstance(node.get('jobLocation'),list)
                                          else [node.get('jobLocation',{})])]
        places=[x for x in places if x]
        place=next((x for x in places if bangladesh_relevance(x)), '; '.join(places))
        is_remote='TELECOMMUTE' in str(node.get('jobLocationType','')).upper()
        remote_scope=location_text(node.get('applicantLocationRequirements'))
        if is_remote and remote_scope:
            region_info=classify_region(remote_scope,desc,remote=True)
        elif place:
            region_info=classify_region(place,desc,remote=is_remote)
        elif is_remote:
            region_info=classify_region('Remote',desc,remote=True)
        else:
            # These pages are discovered from the Bangladesh employer registry;
            # retain missing-location leads explicitly as unverified.
            region_info={'region':'Bangladesh','location':'Bangladesh (verify location)'}
        if not region_info:continue
        place=region_info.pop('location')
        remote = 'Remote' if is_remote else 'Not specified'
        reqparts=[clean_text(node.get(k,''),2400) for k in ('qualifications','experienceRequirements','educationRequirements')]
        html_reqs,html_responsibilities=extract_role_sections(soup)
        reqs=[part for part in reqparts if part] or html_reqs
        responsibility=clean_text(node.get('responsibilities',''),4000)
        responsibilities=[responsibility] if responsibility else html_responsibilities
        app=node.get('directApply')  # Boolean is *not* an application URL.
        _=app
        url=node.get('url') or page_url
        if isinstance(url,str): url=urljoin(page_url,url)
        if not isinstance(url,str) or not valid_url(url): url=page_url
        identifier=node.get('identifier')
        if isinstance(identifier,dict): identifier=identifier.get('value') or identifier.get('name')
        identifier=clean_text(identifier,150)
        shared_listing=not node.get('url') and not is_job_detail_url(page_url)
        logo = employer.get('logo','') if isinstance(employer,dict) else ''
        if isinstance(logo,dict): logo=logo.get('url','')
        image = node.get('image')
        if isinstance(image,dict): image=image.get('url','')
        if isinstance(image,list): image=image[0] if image else ''
        companylogo = logo if isinstance(logo,str) and valid_url(logo) else ''
        poster = image if isinstance(image,str) and valid_url(image) else ''
        jobs.append(new_job(title=title,company=company,url=url,source='Official employer',sources=sources,
            description=desc,posted=node.get('datePosted',''),deadline=node.get('validThrough',''),
            location=place,workplace=region_info.pop('workplace',remote),employment_type=value_of(node.get('employmentType')),
            salary=_salary_from_ld(node.get('baseSalary')),
            posting_identifier=identifier,shared_listing_url=shared_listing,
            requirements=reqs,responsibilities=responsibilities,
            apply_url=url,company_logo_url=companylogo,poster_url=poster,
            verification_level='Official structured data',description_status='Full description' if len(desc)>200 else 'Official excerpt',
            **region_info))
    if jobs: return jobs
    # Conservative fallback: require a job-specific URL and an explicit security role in the H1.
    path=urlparse(page_url).path.lower()
    if not re.search(r'/((?:job|position|vacanc|opening|opportunity|career|recruitment)[^/]*/|[^/]+-\d{5,})',path): return []
    h1=soup.find('h1')
    if not h1: return []
    title=clean_text(h1.get_text(' ',strip=True),200)
    main=soup.find('main') or soup.find('article') or soup.body
    if not main: return []
    for elem in main.select('script,style,nav,footer,header,form'): elem.decompose()
    requirements,responsibilities=extract_role_sections(main)
    description=clean_text(main.get_text(' ',strip=True),11000)
    if len(description)<100 or SUSPICIOUS_CONTENT.search(description[:350]): return []
    if not is_relevant(title,description) or not assess_vacancy(title,description,page_url,source_kind='html').vacancy: return []
    og=soup.select_one('meta[property="og:image"]')
    maybe_img=og.get('content','') if og else ''
    if not valid_url(maybe_img): maybe_img=''
    return [new_job(title=title,company=company_hint,url=page_url,source='Official employer',sources=sources,
        description=description,poster_url=maybe_img,requirements=requirements,responsibilities=responsibilities,
        verification_level='Official page parsed',description_status='Page text (review recommended)')]


ATS_HOST_SUFFIXES = ('greenhouse.io', 'lever.co', 'ashbyhq.com', 'workable.com', 'smartrecruiters.com',
                     'recruitee.com', 'bamboohr.com', 'personio.de', 'personio.com', 'breezy.hr', 'myworkdayjobs.com')
MIN_HOST_DELAY = 1.5
MAX_CRAWL_DELAY = 10.0


class CompliantFetcher:
    """Allow-listed, robots.txt-respecting fetcher (thread-safe, polite per host)."""

    def __init__(self, sources: list[dict], session: requests.Session | None=None):
        self.session = session or requests.Session()
        self.session.headers.update({'User-Agent':UA,'Accept':'text/html,application/xhtml+xml,application/json;q=0.8,*/*;q=0.5',
                                     'Accept-Language':'en-US,en;q=0.8,bn;q=0.6'})
        self.sources=sources
        self.robots: dict[str,RobotsPolicy|None] = {}
        self.last_fetch_by_host: dict[str,float]={}
        self.crawl_delay: dict[str,float]={}
        self.discovered_ats: list[dict] = []
        self.ats_redirects: dict[str,str] = {}
        self.resolved_urls: dict[str,str] = {}
        self.robots_sitemaps: dict[str,list[str]] = {}
        self.failures: dict[str,str] = {}
        self._lock = threading.RLock()
        self._host_locks: dict[str,threading.Lock] = {}

    def _host_lock(self, key: str) -> threading.Lock:
        with self._lock:
            return self._host_locks.setdefault(key, threading.Lock())

    def is_official_allowed(self, url: str) -> bool:
        if not valid_url(url):return False
        host=urlparse(url).hostname or ''
        if any(same_host_or_subdomain(host,b) for b in ('linkedin.com','bdjobs.com','indeed.com','glassdoor.com','joblagbe.online','dohaj.com','careerjet.com.bd','jora.com','nextjobz.com','jobs.com.bd')):
            return False
        # Only explicitly listed official career/website hosts and ATS endpoints.
        for src in self.sources:
            if src['sector'] in ('Job portal','Remote job feed') or src.get('mode')=='restricted':continue
            allowed=[src.get('website',''),src.get('careers_url',''),*(src.get('career_alternates') or [])]
            if any(u and same_host_or_subdomain(host,urlparse(u).hostname or '') for u in allowed):return True
        return False

    def robots_allow(self, url: str) -> bool:
        """RFC 9309: longest-match rules, wildcards, 4xx = no restrictions, 5xx/network = disallow.

        Ordinary robots.txt redirects to approved canonical hosts are followed.
        A server/network failure is never treated as permission.
        """
        parts = urlparse(url)
        key = f'{parts.scheme}://{parts.netloc}'
        with self._host_lock('robots:'+key):
            if key not in self.robots:
                self.robots[key] = self._load_robots(key, url)
        rp=self.robots[key]
        allowed = rp is not None and rp.can_fetch(UA,url)
        if rp is not None and not allowed:
            self.failures[url] = 'robots.txt disallows this path'
        return allowed

    def _load_robots(self, key: str, url: str) -> RobotsPolicy | None:
        robots_url = key + '/robots.txt'
        try:
            for _ in range(5):
                response = self.session.get(robots_url, timeout=HTTP_TIMEOUT, allow_redirects=False)
                if response.status_code in (301,302,303,307,308):
                    target = urljoin(robots_url,response.headers.get('Location',''))
                    if target == robots_url or not (self.is_official_allowed(target) or
                            same_host_or_subdomain(urlparse(target).hostname or '', urlparse(key).hostname or '')):
                        self.failures[url] = 'robots.txt redirects outside approved employer hosts'
                        return None
                    robots_url = target
                    continue
                code = response.status_code
                if 400 <= code < 500 and code != 429:
                    # RFC 9309 §2.3.1.3: robots.txt "unavailable" -> no crawl restrictions.
                    return ALLOW_ALL
                if response.ok and len(response.content) <= 512 * 1024:
                    if re.search(r'<title[^>]*>[^<]*(?:just a moment|access denied|captcha|verify you are human|request blocked)', response.text[:5000], re.I):
                        self.failures[url] = 'robots.txt returned an access challenge; crawl policy unavailable'
                        return None
                    policy = RobotsPolicy(response.text)
                    self.robots_sitemaps[key] = [u.strip() for u in re.findall(
                        r'^\s*Sitemap\s*:\s*(https?://\S+)', response.text, re.I | re.M)
                        if valid_url(u.strip()) and self.is_official_allowed(u.strip())][:10]
                    delay = policy.crawl_delay(UA)
                    if delay:
                        self.crawl_delay[urlparse(key).netloc] = min(MAX_CRAWL_DELAY, delay)
                    return policy
                self.failures[url] = f'robots.txt HTTP {code} (server error: treated as disallow)'
                return None
            self.failures[url] = 'Too many robots.txt redirects'
        except requests.Timeout:
            self.failures[url] = 'robots.txt request timed out'
        except requests.ConnectionError:
            self.failures[url] = 'robots.txt DNS/network connection failed'
        except requests.RequestException:
            self.failures[url] = 'robots.txt request failed'
        return None

    def _polite_wait(self, host: str) -> None:
        delay = max(MIN_HOST_DELAY, self.crawl_delay.get(host, 0))
        elapsed = time.monotonic() - self.last_fetch_by_host.get(host, 0)
        if host in self.last_fetch_by_host and elapsed < delay:
            time.sleep(delay - elapsed)
        self.last_fetch_by_host[host] = time.monotonic()

    def fetch(self, url: str, *, xml: bool = False, depth: int = 0) -> str | None:
        if not self.is_official_allowed(url):
            self.failures[url] = 'Not an approved employer host'
            return None
        if not self.robots_allow(url):
            self.failures.setdefault(url,'Robots policy unavailable or disallows this URL')
            return None
        host = urlparse(url).netloc
        for attempt in range(2):
            try:
                with self._host_lock(host):
                    self._polite_wait(host)
                    response = self.session.get(url, timeout=HTTP_TIMEOUT, allow_redirects=False)
                if response.status_code in (301, 302, 303, 307, 308):
                    if depth >= 5:
                        self.failures[url] = 'Too many page redirects'
                        return None
                    target = urljoin(url, response.headers.get('Location', ''))
                    target_host = (urlparse(target).hostname or '').lower()
                    if any(same_host_or_subdomain(target_host, s) for s in ATS_HOST_SUFFIXES):
                        # Career page hands off to a public ATS: read it through its API instead.
                        self.ats_redirects[url] = target
                        self.failures[url] = 'Redirects to a public ATS board (read via ATS API)'
                        return None
                    if target != url and self.is_official_allowed(target):
                        body = self.fetch(target, xml=xml, depth=depth + 1)
                        if body is None:
                            self.failures[url] = self.failures.get(target,'Redirect target unavailable')
                        else:
                            self.resolved_urls[url] = self.resolved_urls.get(target, target)
                        return body
                    self.failures[url] = 'Page redirects outside approved employer hosts'
                    return None
                if response.status_code in (429,500,502,503,504) and attempt == 0:
                    # Backoff for transient server conditions; no challenge solving.
                    if response.status_code == 429:
                        self.failures[url] = 'HTTP 429 rate limited; try again later'
                        retry = str(response.headers.get('Retry-After', '')).strip()
                        if retry.isdigit():
                            self.crawl_delay[host] = min(MAX_CRAWL_DELAY * 3, float(retry))
                        return None
                    time.sleep(1.0)
                    continue
                if not response.ok:
                    self.failures[url] = f'HTTP {response.status_code}'
                    return None
                if len(response.content) > 4 * 1024 * 1024:
                    self.failures[url] = 'Page exceeds size budget (4 MB)'
                    return None
                content_type = response.headers.get('content-type', response.headers.get('Content-Type', 'text/html')).lower()
                if xml:
                    if not any(x in content_type for x in ('xml','text/plain','rss','atom')):
                        self.failures[url] = 'Expected an XML sitemap/feed'
                        return None
                elif not any(x in content_type for x in ('text/html','application/xhtml+xml')):
                    if not ('text/plain' in content_type and response.text.lstrip()[:30].lower().startswith(('<html','<!doctype'))):
                        self.failures[url] = 'Not an HTML page'
                        return None
                body=response.text
                if not xml:
                    title=re.search(r'<title[^>]*>(.*?)</title>',body[:16000],re.I|re.S)
                    page_title=clean_text(title.group(1),250).lower() if title else ''
                    if re.search(r'\b(just a moment|access denied|captcha|verify you are human|robot check|bot detection|request blocked|attention required)\b',page_title):
                        self.failures[url] = 'Access challenge or blocking page received'
                        return None
                    if re.search(r'\b(?:404|page\s+not\s+found|page\s+does\s+not\s+exist|page\s+unavailable)\b',page_title):
                        self.failures[url] = 'Soft 404: missing page returned HTTP 200'
                        return None
                self.failures.pop(url,None)
                self.resolved_urls[url] = url
                return body
            except requests.exceptions.SSLError:
                self.failures[url]='TLS certificate validation failed'
                return None
            except requests.Timeout:
                if attempt == 0:
                    time.sleep(0.6)
                    continue
                self.failures[url]='Page request timed out twice'
            except requests.ConnectionError:
                if attempt == 0:
                    time.sleep(0.6)
                    continue
                self.failures[url]='Page DNS/network connection failed twice'
            except requests.RequestException:
                self.failures[url]='Page request failed'
                return None
        return None

    def render(self, url: str) -> str | None:
        """Optional JavaScript rendering (Playwright) for robots-permitted SPA career pages."""
        from .render import render_page
        if not self.is_official_allowed(url) or not self.robots_allow(url):
            return None
        host = urlparse(url).netloc
        with self._host_lock(host):
            self._polite_wait(host)
            body = render_page(url, UA, allow_navigation=lambda u: self.is_official_allowed(u) and self.robots_allow(u))
            if body is None:
                self.failures[url] = 'JavaScript rendering unavailable or failed; install Chromium and check rendering logs'
            return body

    def fetch_pdf(self, url: str) -> bytes | None:
        """Read only small official, public PDF vacancy circulars.

        This does not defeat access controls, parse CAPTCHA pages, or fetch
        unapproved hosts. Size and page-count limits protect the collector.
        """
        if not is_pdf_url(url):
            return None
        if not self.is_official_allowed(url) or not self.robots_allow(url):
            return None
        host = urlparse(url).netloc
        try:
            with self._host_lock(host):
                self._polite_wait(host)
                r = self.session.get(url, timeout=HTTP_TIMEOUT, allow_redirects=False, stream=True)
            if not r.ok or r.is_redirect:
                return None
            if int(r.headers.get('Content-Length', '0') or 0) > 8 * 1024 * 1024:
                return None
            if 'pdf' not in r.headers.get('Content-Type','application/pdf').lower():
                return None
            content = b''
            for chunk in r.iter_content(65536):
                content += chunk
                if len(content) > 8 * 1024 * 1024:
                    return None
            return content if content.startswith(b'%PDF-') else None
        except (requests.RequestException, ValueError):
            return None


def is_pdf_url(url: str) -> bool:
    """Recognise published PDF URLs, including Liferay and download.php links."""
    if not valid_url(url):return False
    parts=urlparse(url)
    if re.search(r'\.pdf(?:/|$)',parts.path,re.I):return True
    return any(re.search(r'\.pdf$',value,re.I) for values in parse_qs(parts.query).values() for value in values)


def circular_pdf_links(htmltext: str, base_url: str, *, limit: int = 3) -> list[str]:
    soup = BeautifulSoup(htmltext,'lxml')
    links = []
    for link in soup.select('a[href]'):
        url = urljoin(base_url, link.get('href',''))
        if not is_pdf_url(url):
            continue
        text = clean_text(link.get_text(' ', strip=True),140)
        path = urlparse(url).path.lower()
        if not re.search(r'job|vacanc|recruit|career|circular|employment|security|position|opportunit|নিয়োগ|নিয়োগ|চাকরি|সার্কুলার|নিরাপত্তা',path+' '+text,re.I):
            continue
        if url not in links:
            links.append(url)
        if len(links)>=limit:break
    return links


def parse_pdf_circular(content: bytes, url: str, company: str, sources: list[dict]) -> list[dict]:
    """Extract job-title leads from text-based bank vacancy PDFs, no OCR.

    Some PDF circulars lack usable text, and those are skipped rather than
    inventing titles from a general company address/boilerplate.
    """
    from pypdf import PdfReader
    logging.getLogger('pypdf').setLevel(logging.ERROR)
    try:
        reader = PdfReader(io.BytesIO(content), strict=False)
        if len(reader.pages)>24 or not len(reader.pages):return []
        full = '\n'.join((page.extract_text() or '') for page in reader.pages[:10])[:24000]
    except Exception:
        return []
    if not re.search(r'\b(job|career|recruit|vacanc|application|circular|position)\b|'+BANGLA_JOB_WORDS, full,re.I):
        return []
    matches = []
    for rawline in full.splitlines():
        line = clean_text(rawline,160)
        if len(line)<4 or len(line)>125:
            continue
        if not is_relevant(line):continue
        if not has_role_title(line):
            continue
        if re.search(r'^(?:experience|knowledge|minimum|qualification|skill|department|reporting|about|contact|address|phone|eligibility)\b',line,re.I):
            continue
        if not assess_vacancy(line,full,url,source_kind='pdf').vacancy:continue
        if line not in matches:matches.append(line)
        if len(matches)>=8:break
    return [new_job(title=t,company=company,url=url,apply_url=url,source='Official PDF circular',sources=sources,
        description=clean_text(full,9000),verification_level='Official PDF circular',
        description_status='Text-extracted PDF · confirm job-specific details and application procedure',
        location='Bangladesh (verify location)') for t in matches]


def discover_job_rss(htmltext: str, base_url: str, limit: int = 2) -> list[str]:
    """Look for officially advertised job/career RSS/Atom feeds on same host."""
    soup = BeautifulSoup(htmltext, 'lxml')
    links = []
    for link in soup.select('link[rel~=alternate][href], a[href]'):
        value = link.get('href','')
        target = urljoin(base_url,value)
        if not valid_url(target):continue
        if not same_host_or_subdomain(urlparse(target).hostname or '',urlparse(base_url).hostname or ''):continue
        label = (value + ' ' + clean_text(link.get_text(' ',strip=True),100)).lower()
        mime = link.get('type','').lower()
        if not re.search(r'career|recruit|job|vacanc|employment|চাকরি|নিয়োগ|নিয়োগ',label):continue
        if 'rss' not in label and 'feed' not in label and 'atom' not in label and 'xml' not in mime:continue
        if target not in links:links.append(target)
        if len(links)>=limit:break
    return links


def parse_job_rss(xmltext: str, source_url: str, company: str, sources: list[dict]) -> list[dict]:
    try:root=ET.fromstring(xmltext)
    except ET.ParseError:return []
    jobs=[]
    for node in root.iter():
        if node.tag.split('}')[-1].lower() not in ('item','entry'):continue
        fields={x.tag.split('}')[-1].lower(): (x.text or '') for x in node if len(x)==0}
        title=clean_text(fields.get('title'),180)
        desc=clean_text(fields.get('description') or fields.get('summary') or fields.get('content'),8000)
        if not is_relevant(title,desc):continue
        link=fields.get('link') or ''
        if not link:
            link_el=next((x for x in node if x.tag.split('}')[-1].lower()=='link'),None)
            link=link_el.get('href','') if link_el is not None else ''
        link=urljoin(source_url,link)
        if not valid_url(link) or not same_host_or_subdomain(urlparse(link).hostname or '',urlparse(source_url).hostname or ''):continue
        if not assess_vacancy(title,desc,link,source_kind='official_rss').vacancy:continue
        jobs.append(new_job(title=title,company=company,url=link,apply_url=link,source='Official employer RSS',sources=sources,
            description=desc,posted=fields.get('pubdate') or fields.get('published') or '',
            verification_level='Official page parsed',description_status='Official RSS excerpt',
            location='Bangladesh (verify location)'))
    return jobs


def candidate_links(page_html: str, base_url: str, budget=8) -> list[str]:
    soup=BeautifulSoup(page_html,'lxml')
    candidates={}
    for a in soup.select('a[href]'):
        label=clean_text(a.get_text(' ',strip=True),240)
        href=urljoin(base_url,a.get('href',''))
        if not valid_url(href):continue
        # Same site only, unless the official career page links to a known ATS.
        path=urlparse(href).path.lower()
        joblike = bool(re.search(r'(?:/job[s]?/|/position[s]?/|/openings?/|/vacanc(?:y|ies)/|/recruitment/|/jobsearch|/job-details/|/careers/.+|/job-\d+|/vacancy-\d+)',path))
        score=3 if is_relevant(label) else 0
        if joblike and re.search(r'(?:cyber|security|risk|audit|it[-_]?governance|soc|infosec|সাইবার|নিরাপত্তা|নিরীক্ষা)', path, re.I):
            score=max(score,2)
        # Job cards often put the title in a sibling heading and give the link
        # only a label such as "View details". Inspect the nearest small card,
        # never the entire listing where unrelated roles would share context.
        if joblike or re.fullmatch(r'(?:view|read)\s+(?:job\s+)?details|apply(?:\s+now)?|বিস্তারিত',label,re.I):
            node=a.parent
            for _ in range(3):
                if node is None:break
                card=clean_text(node.get_text(' ',strip=True),1600)
                if len(card)>1400:break
                headings=node.select('h1,h2,h3,h4,h5,h6')
                if len(headings)==1 and is_relevant(headings[0].get_text(' ',strip=True),card):
                    score=max(score,2);break
                node=node.parent
        if joblike and re.search(r'\b(?:principal\s+officer|(?:it|ict|technology)\s+(?:officer|manager|engineer)|(?:network|system)\s+engineer)\b',label,re.I):
            score=max(score,1)
        if score:candidates[href]=max(candidates.get(href,0),score)
    return [url for url,_ in sorted(candidates.items(),key=lambda x:-x[1])[:max(0,budget)]]




def discover_career_links(page_html: str, base_url: str, limit: int = 5) -> list[str]:
    """Find genuine career/vacancy navigation links on official company websites."""
    soup=BeautifulSoup(page_html,'lxml')
    root_host=urlparse(base_url).hostname or ''
    candidates=[]
    for link in soup.select('a[href]'):
        text=clean_text(link.get_text(' ',strip=True),100).lower()
        url=urljoin(base_url,link.get('href',''))
        # In-page #vacancies navigation does not load a second listing. Keep
        # actual SPA hash routes for the renderer, but skip ordinary anchors.
        if urlparse(url).fragment and not urlparse(url).fragment.startswith(('/', '!/')):
            url=url.split('#',1)[0]
        if not valid_url(url):continue
        if not same_host_or_subdomain(urlparse(url).hostname or '',root_host):continue
        path=(urlparse(url).path+' '+urlparse(url).query).lower()
        if not (re.search(r'\b(career|vacanc|recruit|work with us|join us|job openings|available jobs|employment opportunities|job circular)|\b(?:open|current|view|available)\s+(?:roles|positions|openings|vacancies|jobs)',text+' '+path) or re.search(BANGLA_JOB_WORDS, text+' '+path)):
            # In a slug career links are often 'careers' and lack word boundary at the end.
            if not re.search(r'career|vacanc|recruit|(?:/|-)jobs|job-list|join-us|apply-jobs|চাকরি|নিয়োগ|নিয়োগ',path):continue
        if any(t in path for t in ('login','signin','privacy','sitemap','internship-course')):continue
        if url not in candidates and url.rstrip('/')!=base_url.rstrip('/'):candidates.append(url)
        if len(candidates)>=limit:break
    return candidates

def _sitemap_locs(data: str) -> tuple[list[str], bool]:
    try:
        node = ET.fromstring(data)
    except ET.ParseError:
        return [], False
    is_index = node.tag.split('}')[-1].lower() == 'sitemapindex'
    return [e.text.strip() for e in node.iter() if e.tag.endswith('loc') and e.text], is_index


JOB_PATH = re.compile(r'(?:cyber|infosec|information-security|security-|security_|job[s]?/|vacanc|career[s]?/|recruitment/|opening|position|circular|নিয়োগ|চাকরি)', re.I)


def sitemap_candidates(fetcher: CompliantFetcher, base_url: str, *, limit: int = 12, budget=None) -> list[str]:
    """Targeted sitemap fallback for jobs not linked on landing pages.

    Reads /sitemap.xml (plus Sitemap: lines from robots.txt). For a sitemap
    index only child sitemaps whose names look job-related are opened (max 3).
    Every selected detail URL must pass the same allowlist and robots checks.
    """
    parts=urlparse(base_url)
    if not parts.hostname: return []
    origin=f'{parts.scheme}://{parts.netloc}'
    roots=list(dict.fromkeys([*(getattr(fetcher, 'robots_sitemaps', {}).get(origin, [])), origin+'/sitemap.xml']))
    found=[]; opened=0
    queue=list(roots)
    seen=set()
    while queue and opened<4 and len(found)<limit:
        sm=queue.pop(0)
        if sm in seen:continue
        seen.add(sm)
        if budget is not None and not budget.take():break
        opened+=1
        data=fetcher.fetch(sm,xml=True)
        if not data or len(data)>2_000_000:continue
        locs,is_index=_sitemap_locs(data)
        if is_index:
            children=[u for u in locs if re.search(r'job|career|vacanc|recruit|position|opening',u,re.I)]
            # WordPress commonly puts recruitment pages in page-sitemap.xml.
            # Try that published index entry when no recruiting sitemap exists.
            if not children:
                children=[u for u in locs if re.search(r'(?:page[-_]?sitemap|sitemap[-_]?pages?)',u,re.I)]
            children=[u for u in children if valid_url(u) and fetcher.is_official_allowed(u)]
            queue.extend(children[:3])
            continue
        for url in locs:
            if not valid_url(url) or not same_host_or_subdomain(urlparse(url).hostname or '',parts.hostname):continue
            if JOB_PATH.search(urlparse(url).path):
                if url not in found and fetcher.is_official_allowed(url):found.append(url)
            if len(found)>=limit:break
    return found


def title_from_result(result: dict) -> tuple[str,str]:
    value=clean_text(result.get('title'),280)
    # Strip common page provider suffixes.
    value=re.sub(r'\s+[|–-]\s+(?:LinkedIn|Bdjobs(?:\.com)?|Job Lagbe|Dohaj|Indeed).*$','',value,flags=re.I)
    company=''
    # LinkedIn search titles: "Acme Bank hiring Information Security Officer in Dhaka, Bangladesh"
    m=re.match(r'(.{2,120}?)\s+hiring\s+(.{3,150}?)(?:\s+in\s+(.{3,100}))?$',value,re.I)
    if m and is_relevant(m.group(2)):
        return m.group(2).strip(),m.group(1).strip()
    m=re.match(r'(.{3,150}?)\s+(?:at|\u098f)\s+(.{3,120})$',value,re.I)
    if m:
        return m.group(1).strip(),m.group(2).strip()
    m=re.match(r'(.{3,150}?)\s*:\s*(.{3,120})$',value)
    if m and is_relevant(m.group(1)):
        return m.group(1).strip(),m.group(2).strip()
    return value,''


def provider_of(url: str) -> str:
    h=(urlparse(url).hostname or '').lower()
    for domain, label in (('linkedin.com', 'LinkedIn'), ('bdjobs.com', 'Bdjobs'),
                          ('indeed.com', 'Indeed'), ('glassdoor.com', 'Glassdoor'),
                          ('joblagbe.online', 'Job Lagbe'), ('dohaj.com', 'Dohaj')):
        if same_host_or_subdomain(h, domain):
            return label + ' index'
    if any(same_host_or_subdomain(h,d) for d in ('lever.co','greenhouse.io','ashbyhq.com')):return 'ATS index'
    return 'Search discovery'


def infer_company_from_snippet(snippet: str) -> str:
    m=re.search(r'(?:Company Name|Company|Hiring Organization)\s*:\s*([^.|\n]{3,85})',snippet,re.I)
    return clean_text(m.group(1),100) if m else ''



def _salary_from_ld(value: Any) -> str:
    if not isinstance(value, dict):
        return clean_text(value, 120) if isinstance(value, str) else ''
    amount = value.get('value')
    currency = value.get('currency') or ''
    if isinstance(amount, dict):
        low, high = amount.get('minValue'), amount.get('maxValue')
        unit = amount.get('unitText') or ''
        num = amount.get('value')
        parts = [str(x) for x in (low, high) if x not in (None, '')] or ([str(num)] if num not in (None, '') else [])
        return clean_text(f"{currency} {'–'.join(parts)} {('/ ' + unit.lower()) if unit else ''}", 120) if parts else ''
    return clean_text(f'{currency} {amount}', 120) if amount else ''


def classify_region(location: str, description: str = '', *, remote: bool = False) -> dict | None:
    """Route a posting to the Bangladesh or International dashboard, or None.

    International roles are kept only when the publisher explicitly says the
    role is worldwide / APAC / Bangladesh-eligible remote work.
    """
    from .free_feeds import confidence, text_location_eligibility
    loc = clean_text(location, 300)
    if location_excludes_bangladesh(loc, description):
        return None
    if bangladesh_relevance(loc, description):
        return {'region': 'Bangladesh', 'location': loc or 'Bangladesh (verify location)'}
    if remote or re.search(r'\b(remote|anywhere|worldwide|world wide|global|home[- ]based|work from home|distributed)\b', loc, re.I):
        eligibility = text_location_eligibility(loc, allow_unknown=False)
        if not eligibility and (not loc or re.fullmatch(r'remote|work from home|distributed',loc,re.I)):
            scope = re.search(r'\b(?:work\s+from|remote\s*[:—–-]?|hiring\s+(?:in|from)|applicants?\s+(?:in|from))\s*'
                              r'(worldwide|anywhere\s+in\s+the\s+world|anywhere|globally|apac|asia[- ]pacific|south\s+asia)\b',description,re.I)
            if scope: eligibility = text_location_eligibility(scope.group(1), allow_unknown=False)
        if eligibility:
            return {'region': 'International', 'location': loc or 'Remote', 'workplace': 'Remote',
                    'eligibility': eligibility, 'eligibility_confidence': confidence(eligibility),
                    'company_sector': 'International employer'}
    return None


BD_LOCATION_PATTERN = re.compile(r'\b(bangladesh|bd|dhaka|chattogram|chittagong|sylhet|rajshahi|khulna|rangpur|barishal|barisal|mymensingh|gazipur|narayanganj|cumilla|comilla|bogura|bogra|uttara|gulshan|mirpur|banani|motijheel|cox.s bazar)\b|বাংলাদেশ|ঢাকা|চট্টগ্রাম|সিলেট', re.I)
FOREIGN_LOCATION_PATTERN = re.compile(r'\b(?:United States|USA|U\.S\.(?:A\.)?|US|United Kingdom|UK|UAE|United Arab Emirates|'
    r'Canada|Australia|New Zealand|Germany|France|Ireland|Netherlands|Belgium|Spain|Portugal|Italy|Poland|Sweden|Norway|Denmark|Finland|'
    r'Switzerland|Austria|Czechia|Czech Republic|Romania|Europe|European Union|European Economic Area|EU|EEA|'
    r'India|Singapore|Pakistan|Sri Lanka|Nepal|Japan|China|Hong Kong|Taiwan|South Korea|Indonesia|Malaysia|Philippines|Thailand|Vietnam|'
    r'Saudi Arabia|Qatar|Kuwait|Bahrain|Oman|Israel|South Africa|Nigeria|Kenya|Brazil|Mexico|Argentina|Chile|Colombia|'
    r'London|New York|San Francisco|Bengaluru|Bangalore|Mumbai|Hyderabad|Chennai|Delhi|Dubai|Abu Dhabi|Dublin)\b',re.I)
_BD_EXCLUSION = re.compile(r'\b(?:except|excluding|not\s+(?:available|eligible|open)\s+(?:in|to|for))\s+(?:applicants?\s+from\s+)?(?:Bangladesh|BD)\b',re.I)


def location_excludes_bangladesh(location: str, description: str = '') -> bool:
    """Explicit role/candidate restrictions outrank incidental company geography."""
    loc=clean_text(location,500)
    desc=clean_text(description,12000)
    if _BD_EXCLUSION.search(loc+' '+desc):return True
    for text in (loc,desc):
        for restriction in re.finditer(r'\b(?:only\s+(?:in|for|from)\s+[^.;\n]{1,80}|'
                                      r'[^.;\n]{1,70}\b(?:residents?\s+only|citizens?\s+only)|'
                                      r'\b(?:us|usa|uk|uae|europe|eu|india|canada|australia)\s+only|'
                                      r'(?:must\s+(?:be\s+based|reside|live)|candidates?\s+must\s+be\s+(?:based|located))\s+in\s+[^.;\n]{1,80})',text,re.I):
            scope=restriction.group(0)
            if FOREIGN_LOCATION_PATTERN.search(scope) and not BD_LOCATION_PATTERN.search(scope):return True
    return bool(FOREIGN_LOCATION_PATTERN.search(loc) and not BD_LOCATION_PATTERN.search(loc)
                and not re.search(r'\b(worldwide|world wide|anywhere in the world|global|apac|south asia|asia.pacific)\b',loc,re.I))


def bangladesh_relevance(location: str, description: str = '', *, search_index: bool=False, url: str='') -> bool:
    """Require positive Bangladesh evidence. Never assume all remote roles are BD-eligible."""
    location=clean_text(location, 300)
    description=clean_text(description, 2200)
    if location_excludes_bangladesh(location, description): return False
    if BD_LOCATION_PATTERN.search(location): return True
    # A description mentioning Bangladesh is adequate when no known foreign location contradicts it.
    if FOREIGN_LOCATION_PATTERN.search(location):
        return False
    if re.search(r'\b(?:worldwide|apac|asia.pacific|anywhere|global)\b',location,re.I):return False
    if BD_LOCATION_PATTERN.search(description) and not re.fullmatch(r'remote|work from home|distributed',location,re.I): return True
    if re.search(r'\b(?:based|located|work|hiring|position|job\s+location|location|remote)\s*(?:in|from|within|:)?\s*(?:dhaka|bangladesh)\b|'
                 r'\b(?:dhaka|bangladesh)[ -]+based\b',description,re.I):return True
    # Native Bangladeshi jobs-board URLs without explicit location are still Bangladesh-focused.
    host=(urlparse(url).hostname or '').lower()
    return bool(search_index and any(same_host_or_subdomain(host,d) for d in ('bdjobs.com','jobs.com.bd','job.com.bd','dohaj.com')))

def indexed_result_to_job(result: dict, sources: list[dict]) -> dict | None:
    url=result.get('url')
    if not isinstance(url,str) or not valid_url(url):return None
    from .email_alerts import canonical_portal_job
    portal = canonical_portal_job(url)
    if provider_of(url) in ('LinkedIn index','Bdjobs index','Indeed index','Glassdoor index') and not portal:
        return None  # Search/category/company pages are not individual vacancies.
    if portal:
        url = portal[1]
    title,company=title_from_result(result)
    snippets = result.get('extra_snippets') or []
    if isinstance(snippets, str): snippets = [snippets]
    excerpt=clean_text(' '.join(str(x) for x in [result.get('description') or '', *snippets] if x),3000)
    if not is_relevant(title,excerpt):return None
    if not assess_vacancy(title,excerpt,url,source_kind='index').vacancy:return None
    raw_title = clean_text(result.get('title'), 400)
    location = clean_text(result.get('location'), 200)
    # LinkedIn search titles carry the location after the role; retain it even
    # when title_from_result removed it from the display title.
    place = re.search(r'\s+in\s+([^|]{2,130}?)(?:\s*[|]\s*LinkedIn)?$', raw_title, re.I)
    if not location and place:
        location = clean_text(place.group(1), 200)
    if not location:
        place = re.search(r'\b(?:job\s+)?location\s*:\s*([^.;|]{2,100})', excerpt, re.I)
        if place: location = clean_text(place.group(1), 200)
    if bangladesh_relevance(location or raw_title, excerpt, search_index=True, url=url):
        region = {'region':'Bangladesh', 'location': location or 'Bangladesh (verify location)'}
    else:
        region = classify_region(location or raw_title, excerpt)
        if not region: return None
    if re.search(r'\b(no longer accepting applications|job expired|applications are closed|position filled)\b',excerpt,re.I):return None
    if not company: company=infer_company_from_snippet(excerpt)
    if not company:company='Employer not identified'
    return new_job(title=title,company=company,url=url,source=provider_of(url),sources=sources,
        description=excerpt,verification_level='Search indexed (unverified)',description_status='Search excerpt',
        **region)


def _epoch_iso(value: Any) -> str:
    try:
        n=float(value)
        return datetime.fromtimestamp(n/1000 if n>1e11 else n, timezone.utc).date().isoformat()
    except (TypeError, ValueError, OverflowError, OSError):
        return ''


def list_greenhouse(data: Any, company: str, sources: list[dict]) -> list[dict]:
    out=[]
    for item in data.get('jobs',[]) if isinstance(data,dict) else []:
        title=clean_text(item.get('title'),200)
        desc=clean_text(item.get('content'),11000)
        url=item.get('absolute_url','')
        location=(item.get('location') or {}).get('name','')
        if not valid_url(url) or not is_relevant(title,desc):continue
        region=classify_region(location,desc)
        if not region:continue
        out.append(new_job(title=title,company=company,url=url,source='Greenhouse public API',sources=sources,
            posted=item.get('first_published','') or item.get('updated_at',''),deadline=item.get('application_deadline',''),description=desc,
            **region,
            verification_level='Published ATS API',description_status='Full description' if len(desc)>200 else 'Official excerpt'))
    return out


def list_lever(data: Any, company: str, sources: list[dict]) -> list[dict]:
    out=[]
    for item in data if isinstance(data,list) else []:
        title=clean_text(item.get('text'),200)
        desc=clean_text(item.get('descriptionPlain') or item.get('description') or '',11000)
        url=item.get('hostedUrl','')
        categories=item.get('categories') or {}
        location=categories.get('location','') or ', '.join(categories.get('allLocations') or [])
        if not valid_url(url) or not is_relevant(title,desc):continue
        region=classify_region(location,desc,remote=str(item.get('workplaceType','')).lower()=='remote')
        if not region:continue
        out.append(new_job(title=title,company=company,url=url,source='Lever public API',sources=sources,
            posted=_epoch_iso(item.get('createdAt')),description=desc,**region,
            employment_type=categories.get('commitment','Not specified'),
            apply_url=item.get('applyUrl') if valid_url(item.get('applyUrl','')) else url,
            verification_level='Published ATS API',description_status='Full description' if len(desc)>200 else 'Official excerpt'))
    return out



def list_ashby(data: Any, company: str, sources: list[dict]) -> list[dict]:
    out=[]
    for item in data.get('jobs',[]) if isinstance(data,dict) else []:
        title=clean_text(item.get('title'),200)
        desc=clean_text(item.get('descriptionPlain') or item.get('descriptionHtml') or '',11000)
        url=item.get('jobUrl','')
        location=item.get('location','')
        if not valid_url(url) or not is_relevant(title,desc):continue
        region=classify_region(location,desc,remote=bool(item.get('isRemote')))
        if not region:continue
        region.setdefault('workplace','Remote' if item.get('isRemote') else 'Not specified')
        apply_url=item.get('applyUrl','')
        if not valid_url(apply_url):apply_url=url
        out.append(new_job(title=title,company=company,url=url,source='Ashby public API',sources=sources,
            description=desc,posted=item.get('publishedAt',''),**region,
            apply_url=apply_url, verification_level='Published ATS API',
            description_status='Full description' if len(desc)>200 else 'Official excerpt'))
    return out

def _board_api(provider: str, token: str) -> str:
    if provider == 'greenhouse':
        return f'https://boards-api.greenhouse.io/v1/boards/{token}/jobs?content=true'
    if provider == 'lever':
        return f'https://api.lever.co/v0/postings/{token}?mode=json'
    if provider == 'lever_eu':
        return f'https://api.eu.lever.co/v0/postings/{token}?mode=json'
    if provider == 'ashby':
        return f'https://api.ashbyhq.com/posting-api/job-board/{token}?includeCompensation=true'
    return ''


def ats_posting_to_job(item: dict, *, company: str, provider: str, sources: list[dict]) -> dict | None:
    """Normalised ATS posting -> job record (Bangladesh or explicitly eligible remote)."""
    from .ats import SOURCE_LABEL
    title = clean_text(item.get('title'), 200)
    desc = clean_text(item.get('description'), 11000)
    url = item.get('url') or ''
    if not valid_url(url) or not is_relevant(title, desc):
        return None
    region = classify_region(item.get('location') or '', desc, remote=bool(item.get('remote')))
    if not region:
        return None
    apply_url = item.get('apply_url') if valid_url(item.get('apply_url') or '') else url
    return new_job(title=title, company=company, url=url, source=SOURCE_LABEL.get(provider, provider.title() + ' public API'),
                   sources=sources, description=desc, posted=item.get('posted') or '',
                   employment_type=item.get('employment_type') or 'Not specified', apply_url=apply_url,
                   verification_level='Published ATS API',
                   description_status='Full description' if len(desc) > 200 else 'Official excerpt', **region)


def configured_ats_boards(discovered: list[dict] | None = None) -> list[dict]:
    """The exact validated ATS worklist used for both planning and collection."""
    from .ats import FETCHERS
    manually = get_json(DATA / 'ats.json', [])
    known = get_json(DATA / 'ats_discovered.json', [])
    entries = (manually if isinstance(manually,list) else []) + (known if isinstance(known,list) else []) + (discovered or [])
    unique = {}
    for board in entries:
        if isinstance(board, dict) and isinstance(board.get('provider'), str) and isinstance(board.get('board_token'), str):
            unique[(board.get('provider').lower(), board.get('board_token').lower())] = board
    return [b for b in unique.values()
              if b.get('company') and re.fullmatch(r'[A-Za-z0-9_.|-]{2,160}', b.get('board_token', ''))
              and b.get('provider', '').lower() in ('greenhouse', 'lever', 'lever_eu', 'ashby', *FETCHERS)][:250]


def _ats_task(board: dict) -> dict:
    return {'source_id': f"ats:{board['provider'].lower()}:{board['board_token'].lower()}",
            'name': board['company'], 'sector': 'ATS boards', 'mode': 'ATS API'}


def ats_jobs(session:requests.Session, sources:list[dict], discovered: list[dict] | None=None, on_source=None,
             *, workers: int | None = None) -> tuple[list[dict],list[dict]]:
    """Read every known public ATS board (manual, previously discovered, discovered this run)."""
    from .ats import FETCHERS
    boards = configured_ats_boards(discovered)
    wants = lambda title: _relevance.assess(title).relevant or bool(re.search(r'\bsecurity\b|\bcyber|\brisk\b|\baudit', title or '', re.I))  # noqa: E731

    def check(item: dict) -> tuple[dict, list[dict]]:
        provider = item['provider'].lower(); token = item['board_token']; company = item['company']
        task = _ats_task(item)
        source_id = task['source_id']
        source_started(on_source, task)
        try:
            coverage_limited=False;coverage_notes=[]
            if provider in FETCHERS:
                from .ats import fetch_board
                raw = fetch_board(session, provider, token, UA, wants)
                new = [j for j in (ats_posting_to_job(r, company=company, provider=provider, sources=sources) for r in raw) if j]
                coverage_limited=bool(getattr(raw,'coverage_limited',False))
                coverage_notes=getattr(raw,'coverage_notes',[])
            else:
                r = session.get(_board_api(provider, token), timeout=HTTP_TIMEOUT, headers={'User-Agent': UA, 'Accept': 'application/json'})
                r.raise_for_status()
                data = r.json()
                if provider in ('lever','lever_eu'):
                    if not isinstance(data,list):raise ValueError('ATS response did not contain a postings array')
                elif not isinstance(data,dict) or not isinstance(data.get('jobs'),list):
                    raise ValueError('ATS response did not contain a jobs array')
                new = (list_greenhouse(data, company, sources) if provider == 'greenhouse'
                       else list_lever(data, company, sources) if provider in ('lever', 'lever_eu')
                       else list_ashby(data, company, sources))
            return ({'name': company, 'source_id': source_id, 'sector': 'ATS boards', 'state': 'partial' if coverage_limited else 'ok',
                     'jobs_found': len(new), 'mode': 'ATS API', 'coverage_limited':coverage_limited,
                     'collection_complete':not coverage_limited,'reason_code':'incomplete_scan' if coverage_limited else 'ats_complete',
                     'message': f'{provider} board {token}'+('; '+'; '.join(coverage_notes) if coverage_notes else '')}, new)
        except PermissionError as e:
            return ({'name': company, 'source_id': source_id, 'sector': 'ATS boards', 'state': 'error',
                     'jobs_found': 0, 'mode': 'ATS API', 'message': str(e)}, [])
        except (requests.RequestException, ValueError, KeyError, TypeError, AttributeError) as e:
            status = getattr(getattr(e, 'response', None), 'status_code', None)
            return ({'name': company, 'source_id': source_id, 'sector': 'ATS boards', 'state': 'error',
                     'jobs_found': 0, 'mode': 'ATS API',
                     'message': f'HTTP {status}' if status else f'HTTP/connection error ({type(e).__name__})'}, [])
        except Exception as e:  # XML parse errors and other provider-format surprises
            return ({'name': company, 'source_id': source_id, 'sector': 'ATS boards', 'state': 'error',
                     'jobs_found': 0, 'mode': 'ATS API', 'message': f'Unexpected board format ({type(e).__name__})'}, [])

    jobs=[]; health=[]
    lock = threading.Lock()
    n = workers or int(os.environ.get('COLLECT_WORKERS', '6') or 6)
    results: dict[int, tuple[dict, list[dict]]] = {}
    with ThreadPoolExecutor(max_workers=max(1, min(n, 16))) as pool:
        futures = {pool.submit(check, b): i for i, b in enumerate(boards)}
        for fut in as_completed(futures):
            outcome, new = fut.result()
            with lock:
                results[futures[fut]] = (outcome, new)
                if on_source: on_source(outcome, new)
    for i in sorted(results):
        health.append(results[i][0]); jobs.extend(results[i][1])
    return jobs,health


ATS_LINK_HOSTS = {
    'boards.greenhouse.io': 'greenhouse', 'job-boards.greenhouse.io': 'greenhouse',
    'jobs.lever.co': 'lever', 'jobs.ashbyhq.com': 'ashby',
}


def discover_ats_links(page_html: str, page_url: str, company: str) -> list[dict]:
    """Extract published public board IDs ONLY from the employer's own page.

    Links, iframes, script embeds and redirects are inspected for ten ATS
    providers. Board tokens are never brute-forced or guessed.
    """
    from .ats import discover_boards
    return discover_boards(page_html, page_url, company)


def next_page_links(page_html: str, base_url: str, limit: int = 2) -> list[str]:
    """Pagination links on a vacancy listing (rel=next, 'Next', '»', 'পরবর্তী')."""
    soup = BeautifulSoup(page_html, 'lxml')
    host = urlparse(base_url).hostname or ''
    out = []
    for a in soup.select('a[href]'):
        label = clean_text(a.get_text(' ', strip=True), 40).lower()
        rel = ' '.join(a.get('rel') or []).lower()
        if 'next' in rel or label in ('next', 'next page', 'next »', '»', '›', '>', 'পরবর্তী', 'more jobs', 'load more') \
                or re.fullmatch(r'next\s*[»›>]?', label):
            url = urljoin(base_url, a.get('href', ''))
            if valid_url(url) and same_host_or_subdomain(urlparse(url).hostname or '', host) and url not in out \
                    and url.rstrip('/') != base_url.rstrip('/'):
                out.append(url)
        if len(out) >= limit:
            break
    return out


class _Budget:
    def __init__(self, total: int):
        self.left = max(0, total)
        self._lock = threading.Lock()

    def take(self) -> bool:
        with self._lock:
            if self.left <= 0:
                return False
            self.left -= 1
            return True


class _FairBudgetPool:
    """Reserve two follow-ups per employer before sharing the extra budget.

    Fast/big websites must not consume every detail request before slower
    employers can follow even their first careers link. Unused reservations
    are returned when an employer finishes.
    """
    def __init__(self,total: int,count: int):
        total=max(0,total)
        reserved=min(2,total//max(1,count))
        self.reserved=[reserved]*count
        self.shared=total-reserved*count
        self.lock=threading.Lock()

    def source(self,index: int):
        pool=self
        class Share:
            @property
            def left(self):
                with pool.lock:return pool.reserved[index]+pool.shared

            def take(self):
                with pool.lock:
                    if pool.reserved[index]>0:
                        pool.reserved[index]-=1;return True
                    if pool.shared>0:
                        pool.shared-=1;return True
                    return False

            def release(self):
                with pool.lock:
                    pool.shared+=pool.reserved[index]
                    pool.reserved[index]=0
        return Share()


def source_failure_reason(message: str) -> tuple[str, str]:
    """Classify a measured failure without treating policy blocks as outages."""
    msg=message.lower()
    if 'robots.txt disallows' in msg:
        return 'robots_disallowed','Use a published feed, subscribed job alerts, or review the employer page manually.'
    if 'robots' in msg:
        return 'robots_unavailable','The crawl policy could not be read; the next hourly run will retry.'
    if '429' in msg:
        return 'rate_limited','Wait for the publisher rate-limit window; the next scheduled run will retry.'
    if 'tls' in msg:
        return 'tls_error','Check the site certificate or a current employer-published URL; TLS checks remain enabled.'
    if '403' in msg or 'challenge' in msg or 'access denied' in msg:
        return 'access_blocked','Use an authorized feed or subscribed alert; this site blocks automated requests.'
    if '404' in msg or '410' in msg:
        return 'page_missing','Review the employer careers URL and its published alternatives.'
    if 'redirects outside' in msg:
        return 'unapproved_redirect','Verify the employer-published destination before adding it to career_alternates.'
    if 'not an approved' in msg:
        return 'restricted_source','Use the supported alert/search import routes for restricted portals.'
    if 'network' in msg or 'dns' in msg or 'timed out' in msg:
        return 'network_error','Retry from the deployment environment; reachability may vary by network.'
    return 'unavailable','Check the recorded HTTP/parser result and the employer current careers page.'


def _check_employer(src: dict, sources: list[dict], fetcher, budget: _Budget) -> tuple[dict, list[dict]]:
    """Check one employer: career page(s), detail links, PDFs, RSS, ATS hand-offs."""
    from . import render as _render
    jobs: list[dict] = []
    discovered = getattr(fetcher, 'discovered_ats', None)
    if discovered is None:
        discovered = []
    ats_redirects = getattr(fetcher, 'ats_redirects', {}) or {}
    can_render = _render.enabled() and hasattr(fetcher, 'render')
    resolved_urls = getattr(fetcher, 'resolved_urls', {})
    checked_urls=[]
    limited=[]
    needs_render=False

    def get_page(url: str, **kwargs):
        if url not in checked_urls:checked_urls.append(url)
        return fetcher.fetch(url, **kwargs)

    def readable_page(url: str, content: str) -> tuple[str, bool]:
        nonlocal needs_render
        shell=_render.looks_js_rendered(content)
        if shell or src.get('render'):
            if can_render:
                rendered_page=fetcher.render(url)
                if rendered_page and not _render.looks_js_rendered(rendered_page):
                    return rendered_page, True
            if shell:
                needs_render=True
        return content, False

    def note_boards(content: str, url: str) -> None:
        for board in discover_ats_links(content, url, src['name']):
            if not any(b.get('provider') == board['provider'] and b.get('board_token') == board['board_token'] for b in discovered):
                discovered.append(board)

    # Prefer a known vacancy page. If it fails, try independently published
    # official alternatives before the corporate homepage. Never fetch an
    # unapproved host or treat a working homepage as a working job board.
    candidates=[]
    for candidate in [src.get('careers_url'),*(src.get('career_alternates') or []),src.get('website')]:
        if candidate and candidate not in candidates and valid_url(candidate):candidates.append(candidate)
    landing='';html=None;attempted=[];ats_handoff=False;rendered=False
    for candidate in candidates:
        page=get_page(candidate)
        if page is not None:
            final_url=resolved_urls.get(candidate,candidate)
            page,did_render=readable_page(final_url,page)
            if not _render.looks_js_rendered(page):
                landing,html=final_url,page
                rendered=did_render
                break
            # Keep the shell for ATS embed discovery, but try a published
            # alternative before treating a JS landing page as usable.
            note_boards(page,final_url)
            attempted.append(f'{urlparse(candidate).netloc}: JavaScript shell; vacancies not extracted')
            continue
        if candidate in ats_redirects:
            note_boards(ats_redirects[candidate], candidate)
            ats_handoff=True
        attempted.append(f'{urlparse(candidate).netloc}: {fetcher.failures.get(candidate,"Unavailable")}')
    if html is None:
        if ats_handoff:
            return ({'name':src['name'],'source_id':src.get('id',src['name']),'sector':src['sector'],'state':'partial','jobs_found':0,
                     'mode':'Official employer','message':'Career page hands off to a public ATS board (checked in ATS phase)',
                     'reason_code':'ats_handoff','checked_urls':len(checked_urls),
                     'collection_complete':False,'coverage_limited':True}, [])
        if needs_render:
            return ({'name':src['name'],'source_id':src.get('id',src['name']),'sector':src['sector'],'state':'partial','jobs_found':0,
                     'mode':'Official employer','message':'JavaScript career page could not be read. Enable RENDER_JS and install Chromium; see ATS checks if a board was discovered.',
                     'reason_code':'javascript_required','checked_urls':len(checked_urls),
                     'collection_complete':False,'coverage_limited':True}, [])
        failure=' | '.join(attempted)[:420] or 'No valid employer website available'
        reason,hint=source_failure_reason(failure)
        return ({'name':src['name'],'source_id':src.get('id',src['name']),'sector':src['sector'],
                 'state':'blocked-or-unavailable','jobs_found':0,'mode':'Official employer',
                 'message':failure,'reason_code':reason,'recovery_hint':hint,'checked_urls':len(checked_urls),
                 'collection_complete':False,'coverage_limited':True}, [])
    career_urls=[src.get('careers_url')]+(src.get('career_alternates') or [])
    career_verified=landing in career_urls or any(resolved_urls.get(u)==landing for u in career_urls if u)
    index_urls=[(landing,html)]
    # A reachable career landing page may only link to the actual job list.
    # Follow published recruiting navigation on both homepages and landing pages.
    for url in discover_career_links(html,landing,limit=5):
        if not budget.take():
            limited.append('recruitment navigation');break
        career_page=get_page(url)
        if career_page:
            final_url=resolved_urls.get(url,url)
            career_page,did_render=readable_page(final_url,career_page)
            rendered=rendered or did_render
            if not _render.looks_js_rendered(career_page):
                index_urls.append((final_url,career_page))
                career_verified=True
            else:
                limited.append('JavaScript vacancy list')
        elif url in ats_redirects:
            note_boards(ats_redirects[url], url); ats_handoff=True
        else:
            limited.append('unavailable recruitment page')
    # Follow next links repeatedly, not just the first next link. Bounds protect
    # against calendar loops and portals with unbounded result pages.
    pagination_seen={u for u,_ in index_urls}
    cursor=0
    try:max_listing_pages=max(1,min(20,int(os.getenv('MAX_LISTING_PAGES','8') or 8)))
    except ValueError:max_listing_pages=8
    while cursor<len(index_urls) and cursor<max_listing_pages:
        url,content=index_urls[cursor];cursor+=1
        for nxt in next_page_links(content, url, limit=2):
            if nxt in pagination_seen:continue
            pagination_seen.add(nxt)
            if len(index_urls)>=max_listing_pages or not budget.take():
                limited.append('listing pagination');break
            page=get_page(nxt)
            if page:
                final_url=resolved_urls.get(nxt,nxt)
                page,did_render=readable_page(final_url,page)
                rendered=rendered or did_render
                if not _render.looks_js_rendered(page):index_urls.append((final_url,page))
                else:limited.append('JavaScript next page')
            else:limited.append('unavailable next page')
    links=[];pdfs=[];feeds=[];n=0
    for index_url, content in index_urls:
        note_boards(content,index_url)
        parsed=scrape_official_job(content,index_url,sources,src['name'])
        jobs.extend(parsed);n+=len(parsed)
        if src.get('sector') in ('Banking','NBFI / financial services','Fintech','Telecom','Public sector','Tech / consulting'):
            for link in circular_pdf_links(content,index_url,limit=4):
                if link not in pdfs:pdfs.append(link)
        for feed in discover_job_rss(content,index_url):
            if feed not in feeds:feeds.append(feed)
        for link in candidate_links(content,index_url,budget=20):
            if link not in links:links.append(link)
    if not links and budget.left>0 and src.get('sector') in ('Banking','Fintech','Telecom','Tech / consulting','Multinational','NBFI / financial services'):
        links=sitemap_candidates(fetcher,landing,limit=15,budget=budget)
    seen_pages={u for u,_ in index_urls}
    for link in links[:24]:
        if not same_host_or_subdomain(urlparse(link).hostname or '',urlparse(landing).hostname or ''):continue
        if link in seen_pages:continue
        if not budget.take():
            limited.append('job detail pages');break
        page=get_page(link)
        if page:
            link=resolved_urls.get(link,link)
            note_boards(page,link)
            found=scrape_official_job(page,link,sources,src['name'])
            if not found and _render.looks_js_rendered(page):
                rendered_page,did_render=readable_page(link,page)
                if did_render:found=scrape_official_job(rendered_page,link,sources,src['name'])
                else:limited.append('JavaScript job detail page')
            jobs.extend(found);n+=len(found)
        else:
            limited.append('unavailable job detail page')
    for pdf in pdfs[:3]:
        if not budget.take():
            limited.append('PDF circulars');break
        if pdf not in checked_urls:checked_urls.append(pdf)
        content=fetcher.fetch_pdf(pdf) if hasattr(fetcher,'fetch_pdf') else None
        if content:
            new=parse_pdf_circular(content,pdf,src['name'],sources)
            jobs.extend(new);n+=len(new)
        else:limited.append('unavailable PDF circular')
    for feed in feeds[:1]:
        if not budget.take():
            limited.append('job RSS feeds');break
        content=get_page(feed,xml=True)
        if content:
            new=parse_job_rss(content,feed,src['name'],sources)
            jobs.extend(new);n+=len(new)
        else:limited.append('unavailable job RSS feed')
    readable_listing=bool(n or links or pdfs or feeds)
    if not readable_listing:
        for _,content in index_urls:
            soup=BeautifulSoup(content,'lxml')
            text=clean_text(soup.get_text(' ',strip=True),16000)
            if get_ld(soup) or re.search(r'\bno\s+(?:(?:new|open|currently?|available|suitable)\s+){0,3}(?:roles?|jobs?|positions?|vacanc(?:y|ies)|openings?)\b|\bno\s+(?:positions?|vacancies)\s+(?:are\s+)?available\b|কোন[োও]?\s+শূন্যপদ\s+নেই',text,re.I):
                readable_listing=True;break
            if any(re.search(r'/(?:jobs?|positions?|openings?|vacancies|vacancy-preview|vacancy-details)/[^/?#]+|jobdetails|job-details',urlparse(urljoin(landing,a.get('href',''))).path,re.I)
                   for a in soup.select('a[href]')):
                readable_listing=True;break
    state='ok' if (career_verified and readable_listing or n) and not limited and not needs_render else 'partial'
    message=('Public career page reachable' if state=='ok' else
             'Company homepage reachable; recruitment page not verified')
    reason='readable_career_page' if state=='ok' else 'homepage_only'
    if career_verified and not readable_listing:
        reason='listing_not_found'
        message='Career landing page reachable, but no vacancy list or explicit no-openings message was found'
    if limited:
        reason='incomplete_scan'
        message='Some source pages were not checked: '+', '.join(dict.fromkeys(limited))
    elif needs_render:
        reason='javascript_required'
        message='Readable fallback found, but a JavaScript vacancy list remains unread; enable RENDER_JS and install Chromium'
    elif ats_handoff and not n:
        state='partial';reason='ats_handoff'
        message='Employer links to an ATS; see the separate ATS result for collection status'
    if rendered:
        message += ' (JavaScript rendered)'
    if attempted:
        message += ' (fallback used; ' + '; '.join(attempted)[:170] + ')'
    return ({'name':src['name'],'source_id':src.get('id',src['name']),'sector':src['sector'],'state':state,'jobs_found':n,
             'mode':'Official employer','message':message,'checked_urls':len(checked_urls),'reason_code':reason,
             'listing_pages':len(index_urls),'collection_complete':state=='ok','coverage_limited':state!='ok',
             'resolved_url':landing,'pdf_candidates':len(pdfs),'rss_candidates':len(feeds)}, jobs)


def coverage_round(sources:list[dict], fetcher:CompliantFetcher, limit:int, detail_budget:int=70, on_source=None,
                   *, workers: int | None = None) -> tuple[list[dict],list[dict]]:
    """Check official employer sites in parallel (polite per host); results keep source order."""
    targets=selected_employers(sources,limit)
    if not targets:return [],[]
    budget_pool=_FairBudgetPool(detail_budget,len(targets))
    n = workers or int(os.environ.get('COLLECT_WORKERS', '6') or 6)
    jobs=[]; health=[]
    lock=threading.Lock()

    def run_one(src,source_budget):
        source_started(on_source, {'source_id': src.get('id') or src['name'], 'name': src['name'],
                                  'sector': src['sector'], 'mode': 'Official employer'})
        try:
            return _check_employer(src, sources, fetcher, source_budget)
        except Exception as exc:  # one malformed site must not abort the scan
            logging.getLogger(__name__).warning('Employer check failed for %s: %s', src.get('name'), exc)
            return ({'name':src['name'],'source_id':src.get('id',src['name']),'sector':src['sector'],
                     'state':'error','jobs_found':0,'mode':'Official employer',
                     'message':f'Parser error ({type(exc).__name__})'}, [])
        finally:
            source_budget.release()

    results: dict[int, tuple[dict, list[dict]]] = {}
    with ThreadPoolExecutor(max_workers=max(1, min(n, 16))) as pool:
        futures = {pool.submit(run_one, t, budget_pool.source(i)): i for i, t in enumerate(targets)}
        for fut in as_completed(futures):
            outcome, found = fut.result()
            with lock:  # callbacks (incremental store + progress) run one at a time
                results[futures[fut]] = (outcome, found)
                if on_source: on_source(outcome, found)
    for i in sorted(results):
        health.append(results[i][0]); jobs.extend(results[i][1])
    return jobs,health


def similarity_key(job: dict) -> str:
    region = job.get('region', 'Bangladesh')
    url = canonical_job_url(job.get('source_url') or job.get('apply_url') or '')
    if url:
        if job.get('posting_identifier'):
            return region + ':' + url + ':req:' + str(job['posting_identifier'])
        if job.get('shared_listing_url'):
            return region + ':' + url + ':role:' + _norm_title(job.get('title',''))
        if urlparse(url).path.lower().endswith('.pdf') or str(job.get('source','')).startswith('Official PDF'):
            return region + ':' + url + ':' + _norm_title(job.get('title', ''))
        return region + ':' + url
    # Legacy/manual seed records without a URL still dedupe semantically.
    company = re.sub(r'[^a-z0-9]+', '', job.get('company', '').lower().replace('limited','').replace('ltd','').replace('plc',''))
    title = re.sub(r'[^a-z0-9]+', '', job.get('title','').lower())
    return region + ':' + company + ':' + title


def deduplicate(jobs: list[dict]) -> list[dict]:
    priority={'Official structured data':8,'Published ATS API':7,'Publisher public API':6,
              'Official page parsed':5,'Official PDF circular':5,'Publisher page verified':4,'Editorially checked':3,
              'Aggregator API':2,'Email alert (subscribed)':2,'User feed (unverified)':1,
              'Search indexed (unverified)':1}
    def rank(j):
        observed=j.get('last_observed_at') or j.get('last_seen_at') or j.get('collected_at') or ''
        return (priority.get(j.get('verification_level',''),2),str(observed),len(j.get('description','')),
                int(bool(j.get('deadline'))))
    unique = {}
    for job in jobs:
        key = similarity_key(job)
        if key not in unique:
            unique[key] = job.copy()
            continue
        current = unique[key]
        winner = job if rank(job) > rank(current) else current
        other = current if winner is job else job
        result = winner.copy()
        for attr in ('deadline', 'company_logo_url', 'poster_url', 'salary', 'requirements',
                     'responsibilities', 'eligibility', 'eligibility_confidence',
                     'source_name', 'source_domain', 'posted_at', 'alert_received_at',
                     'provider_updated_at', 'source_updated_at', 'vacancy_evidence', 'vacancy_reason'):
            if not result.get(attr) or result.get(attr) in ('Not disclosed','Not specified','unconfirmed'):
                if other.get(attr):result[attr]=other[attr]
        result['collected_at'] = min(filter(None,[current.get('collected_at',''),job.get('collected_at','')]),default=today_iso())
        result['last_seen_at'] = max(current.get('last_seen_at',''),job.get('last_seen_at',''))
        for attr in ('last_observed_at','alert_received_at','source_updated_at','provider_updated_at'):
            result[attr] = max(current.get(attr) or '',job.get(attr) or '')
        result['also_listed_on'] = list({entry.get('url'): entry for entry in
            (current.get('also_listed_on') or []) + (job.get('also_listed_on') or [])
            if isinstance(entry, dict) and entry.get('url')}.values())[:12]
        unique[key] = result
    return fold_cross_source(list(unique.values()), rank)


LOW_TIER = {'Search indexed (unverified)', 'Email alert (subscribed)', 'Aggregator API',
            'User feed (unverified)'}


def _norm_company(name: str) -> str:
    name = (name or '').lower()
    name = re.sub(r'\b(limited|ltd\.?|plc|pvt\.?|private|inc\.?|llc|bangladesh|group|co\.?)\b', ' ', name)
    return re.sub(r'[^a-z0-9\u0980-\u09ff]+', '', name)


def _norm_title(title: str) -> str:
    t = (title or '').lower()
    t = re.sub(r'\((?:remote|hybrid|on-?site|contract|full[- ]time)\)|\b(?:sr\.?|senior)\b', lambda m: 'senior' if 'sr' in m.group(0) or 'senior' in m.group(0) else '', t)
    return re.sub(r'[^a-z0-9\u0980-\u09ff]+', '', t)


def fold_cross_source(jobs: list[dict], rank=None) -> list[dict]:
    """Merge the same vacancy seen on an aggregator/search/email *and* elsewhere.

    Only low-confidence copies (search index, job-alert email, aggregator, user
    feed) are folded into a richer record; two distinct official requisitions
    with the same title stay separate. Alternate listings are kept in
    ``also_listed_on`` so no source link is lost.
    """
    rank = rank or (lambda j: (0, len(j.get('description', ''))))
    groups: dict[str, list[int]] = {}
    for i, job in enumerate(jobs):
        company = _norm_company(job.get('company', ''))
        if not company or company.startswith('employernotidentified'):
            continue
        groups.setdefault(f"{job.get('region','Bangladesh')}|{company}|{_norm_title(job.get('title',''))}", []).append(i)
    drop: set[int] = set()
    for idx in groups.values():
        if len(idx) < 2:
            continue
        low = [i for i in idx if jobs[i].get('verification_level') in LOW_TIER]
        high = [i for i in idx if i not in low]
        if not low:
            continue
        # A shared employer/title is not a requisition ID. Several LinkedIn
        # vacancies can have the same title; several official openings can too.
        # Fold only a one-to-one low-trust copy into an unambiguous official one.
        if len(high) != 1:
            continue
        target = high[0]
        publisher_counts: dict[str, int] = {}
        for i in low:
            host = (urlparse(jobs[i].get('source_url') or '').hostname or '').lower().removeprefix('www.')
            if host.endswith('.linkedin.com'): host = 'linkedin.com'
            publisher_counts[host] = publisher_counts.get(host, 0) + 1
        for i in low:
            if i == target:
                continue
            keep, other = jobs[target], jobs[i]
            low_deadline=deadline_date(other.get('deadline'))
            high_deadline=deadline_date(keep.get('deadline'))
            if other.get('vacancy_status') in ('expired','closed') or (low_deadline and low_deadline < today_iso()):
                continue
            if low_deadline and high_deadline and low_deadline != high_deadline:
                continue
            low_observed=iso_date(other.get('last_seen_at') or other.get('alert_received_at'))
            high_observed=iso_date(keep.get('last_seen_at') or keep.get('collected_at'))
            if low_observed and high_observed and (datetime.fromisoformat(high_observed)-datetime.fromisoformat(low_observed)).days > 21:
                continue
            host = (urlparse(other.get('source_url') or '').hostname or '').lower().removeprefix('www.')
            if host.endswith('.linkedin.com'): host = 'linkedin.com'
            if publisher_counts.get(host, 0) > 1:
                continue
            a_city, b_city = textmine.bd_city(keep.get('location', '')), textmine.bd_city(other.get('location', ''))
            if a_city and b_city and a_city != b_city:
                continue
            a_date, b_date = iso_date(keep.get('posted_at')), iso_date(other.get('posted_at'))
            if a_date and b_date and abs((datetime.fromisoformat(a_date) - datetime.fromisoformat(b_date)).days) > 21:
                continue
            listed = keep.setdefault('also_listed_on', [])
            entry = {'source_name': other.get('source_name') or other.get('source'), 'url': other.get('source_url')}
            if entry['url'] and entry['url'] != keep.get('source_url') and entry not in listed and len(listed) < 8:
                listed.append(entry)
            for prev in other.get('also_listed_on') or []:
                if prev not in listed and prev.get('url') != keep.get('source_url') and len(listed) < 8:
                    listed.append(prev)
            for attr in ('deadline', 'posted_at', 'salary', 'company_logo_url'):
                if not keep.get(attr) or keep.get(attr) in ('Not disclosed',):
                    if other.get(attr): keep[attr] = other[attr]
            keep['last_seen_at'] = max(keep.get('last_seen_at', ''), other.get('last_seen_at', ''))
            drop.add(i)
    return [j for i, j in enumerate(jobs) if i not in drop]


def annotate_freshness(jobs: list[dict], age_limit: int = 45) -> list[dict]:
    """Keep observed jobs in storage; mark age/expiry rather than deleting them.

    Silent deletion on day 46 previously caused the apparent loss of postings.
    Never call an unverified posting 'confirmed open'.
    """
    today = now_bd().astimezone(BANGLADESH).date()
    for job in jobs:
        deadline = deadline_date(job.get('deadline'))
        last = iso_date(job.get('last_seen_at') or job.get('collected_at'))
        posted = iso_date(job.get('posted_at'))
        previous_status = str(job.get('vacancy_status') or '').strip().lower()
        if deadline:
            job['deadline'] = deadline
        job['archive_reason'] = ''
        if previous_status == 'closed':
            # A known closure remains closed until a fresh source observation
            # supersedes that record; a future date alone does not reopen it.
            job['vacancy_status'] = 'closed'
            job['archive_reason'] = 'source_closed'
        elif deadline and deadline < today.isoformat():
            job['vacancy_status'] = 'expired'
            job['archive_reason'] = 'deadline_passed'
        elif previous_status == 'expired' and not deadline:
            job['vacancy_status'] = 'expired'
            job['archive_reason'] = 'source_expired'
        elif last and last < (today - timedelta(days=age_limit)).isoformat():
            job['vacancy_status'] = 'older_unverified'
        elif not last and posted and posted < (today - timedelta(days=age_limit)).isoformat():
            job['vacancy_status'] = 'older_unverified'
        else:
            job['vacancy_status'] = 'unverified'
    # The Himalayas public API terms specifically require expired jobs to be
    # removed rather than preserved in an archive. Other sources may remain
    # marked expired, subject to their respective publisher rules.
    return [j for j in jobs if not (j.get('source') == 'Himalayas'
                                   and j.get('vacancy_status') == 'expired')]


def live_filter(jobs:list[dict], age_limit:int)->list[dict]:
    """Keep non-archived leads; age alone means 'verify', never 'expired'.

    This compatibility helper follows the same archive policy as the main
    collector and does not mutate records owned by its caller.
    """
    marked = annotate_freshness([dict(job) for job in jobs], age_limit)
    return [job for job in marked if job.get('vacancy_status') not in ('expired', 'closed')]


def selected_employers(sources: list[dict], limit: int) -> list[dict]:
    """Exactly the employers scheduled in the current local hourly run."""
    eligible=[x for x in sources if (x.get('careers_url') or x.get('website'))
              and x['sector'] not in ('Job portal','Remote job feed','Social media')
              and x.get('mode') not in ('restricted','index','directory','link-only')
              and x.get('name','').strip().casefold() != 'bangladesh bank']
    eligible.sort(key=lambda x: (x.get('sector')!='Banking', x.get('name','')))
    if not eligible or limit<=0:
        return []
    if limit>=len(eligible):
        return eligible
    slot=int(now_bd().timestamp()//3600)
    rotation=(slot*max(1,limit))%len(eligible)
    return [eligible[(rotation+i)%len(eligible)] for i in range(min(limit,len(eligible)))]


def configured_ats_count() -> int:
    return len(configured_ats_boards())


def run(max_queries:int=6,max_career_pages:int=250,max_detail_pages:int=450,
        dry_run:bool=False, *, force_feeds:bool=False, on_progress=None, schedule:dict|None=None)->dict:
    """Run scheduled collection; persist jobs, progress and 10-check health atomically.

    Each source publishes job discoveries as soon as its check completes.
    Restricted job boards and social platforms are present as link-only sources
    but are never silently counted as successfully scraped.
    """
    from .free_feeds import collect_public_feeds, PROVIDERS
    from .telemetry import CollectionTelemetry, IncrementalJobStore
    from . import custom_feeds, email_alerts, search_apis
    sources=get_json(DATA/'sources.json',[])
    sources=[x for x in sources if x.get('name','').strip().casefold() != 'bangladesh bank'
             and x.get('name','').strip().casefold() != 'bangladesh bank e-recruitment']
    previous_status=get_json(DATA/'status.json',{})
    previous_status=previous_status if isinstance(previous_status,dict) else {}
    existing=get_json(DATA/'jobs.json',{'jobs':[]})
    existing=existing if isinstance(existing,dict) else {'jobs':[]}
    previous_jobs=[j for j in existing.get('jobs',[]) if isinstance(j,dict)
                   if j.get('company','').strip().casefold()!='bangladesh bank']
    prior_count=len(previous_jobs)
    rejected: dict[str,dict] = {}
    def persist_rejections() -> None:
        if dry_run or not rejected:return
        old=get_json(DATA/'rejected_jobs.json',{'records':[]})
        records={similarity_key(x['job']):x for x in old.get('records',[])
                 if isinstance(x,dict) and isinstance(x.get('job'),dict)} if isinstance(old,dict) else {}
        records.update(rejected)
        write_json(DATA/'rejected_jobs.json',{'version':'5.2','records':list(records.values())[-1000:]})
    def validated(batch: list[dict], *, previous: bool=False) -> list[dict]:
        accepted=[]
        for item in batch:
            if not isinstance(item,dict) or item.get('company','').strip().casefold()=='bangladesh bank':
                continue
            evidence=assess_record(item)
            geo_excluded=location_excludes_bangladesh(item.get('location',''), item.get('description',''))
            if not evidence.vacancy or geo_excluded:
                key=similarity_key(item)
                rejected.setdefault(key,{'job':dict(item),'reason':'explicit location excludes Bangladesh applicants' if geo_excluded else evidence.reason,
                    'detected_at':now_bd().isoformat(timespec='seconds'), 'previously_published':previous,
                    'detection_version':'5.2'})
                continue
            job=dict(item)
            relevance=_relevance.assess(job.get('title',''),job.get('description',''))
            job.update(relevance_score=relevance.score,relevance_reason=relevance.reason,
                       matched_terms=relevance.terms[:12],vacancy_score=evidence.score,
                       vacancy_reason=evidence.reason,vacancy_evidence=evidence.signals,detection_version='5.2')
            accepted.append(job)
        return accepted
    previous_jobs=validated(previous_jobs,previous=True)
    previous_removed=prior_count-len(previous_jobs)
    # Protect the removed historical rows before any incremental job write.
    persist_rejections()
    previous_keys={similarity_key(j) for j in previous_jobs}
    store=IncrementalJobStore(DATA/'jobs.json', persist=not dry_run)
    store.jobs=previous_jobs
    employer_targets=selected_employers(sources,max(0,min(max_career_pages,250)))
    feeds_cfg=get_json(DATA/'custom_feeds.json',[])
    feeds_cfg=[feed for feed in feeds_cfg if isinstance(feed,dict) and feed.get('enabled',True)
               and valid_url(feed.get('url',''))] if isinstance(feeds_cfg,list) else []
    planned=[{'source_id':'feed:'+name,'name':name,'sector':'Remote job feed','mode':'Free publisher feed'}
             for name in PROVIDERS]
    planned.extend({'source_id':src.get('id') or src['name'],'name':src['name'],
                    'sector':src['sector'],'mode':'Official employer'} for src in employer_targets)
    planned.extend(_ats_task(board) for board in configured_ats_boards())
    if email_alerts.configured():
        planned.append({'source_id':'email:alerts','name':'Job-alert mailbox','sector':'Job alerts','mode':'IMAP (subscribed alerts)'})
    for key,task in (('BRAVE_API_KEY',{'source_id':'api:brave','name':'Brave Search API','sector':'Search API','mode':'Licensed search index'}),
                     ('JOOBLE_API_KEY',{'source_id':'api:jooble','name':'Jooble API','sector':'Aggregator API','mode':'Aggregator API (regional key)'})):
        if os.environ.get(key,'').strip():planned.append(task)
    planned.extend({'source_id':('custom:'+feed['url'])[:200],
                    'name':feed.get('name') or urlparse(feed['url']).hostname,
                    'sector':'Custom feed','mode':'User RSS/Atom feed'} for feed in feeds_cfg)
    planned=list({task['source_id']:task for task in planned}.values())
    monitor=CollectionTelemetry(DATA,total=len(planned),status_callback=on_progress,persist=not dry_run,schedule=schedule)
    monitor.plan_sources(planned)
    prior_completion=monitor.progress.get('last_completed_at')
    prior_success=monitor.progress.get('last_successful_at')
    state=get_json(DATA/'feed_state.json',{})
    session=requests.Session()
    session.headers.update({'User-Agent':UA, 'Accept':'text/html,application/json;q=0.8'})
    fetcher=CompliantFetcher(sources,session)
    errors=[]; health=[]; new_candidates=[]

    def received(outcome: dict, batch: list[dict]) -> None:
        confirmed=validated(batch)
        outcome['raw_jobs_found']=outcome.get('jobs_found',len(batch))
        outcome['rejected_count']=len(batch)-len(confirmed)
        outcome['jobs_found']=len(confirmed)
        added=store.merge_batch(confirmed)
        monitor.completed(source_id=outcome.get('source_id') or outcome.get('name','unknown'),
                          name=outcome.get('name','unknown'),sector=outcome.get('sector','Other'),
                          mode=outcome.get('mode','unknown'), state=outcome.get('state','error'),
                          jobs=outcome.get('jobs_found',len(confirmed)),new_jobs=added,
                          message=outcome.get('message',''),
                          **{key:outcome[key] for key in ('reason_code','resolved_url','checked_url','checked_urls',
                              'listing_pages','collection_complete','recovery_hint','rejected_count','raw_jobs_found',
                              'requests','coverage_limited') if key in outcome})

    def started(outcome: dict) -> None:
        monitor.started(source_id=outcome.get('source_id') or outcome.get('name','unknown'),
                        name=outcome.get('name','unknown'),sector=outcome.get('sector','Other'),
                        mode=outcome.get('mode','unknown'),message=outcome.get('message',''))
    # Keep the existing result-callback signature compatible with custom
    # adapters; upgraded adapters can announce work through this optional hook.
    received.started=started

    try:
        monitor.phase('feeds','Checking public publisher feeds')
        remote,remote_health,feed_state=collect_public_feeds(
            session,sources,state,force=force_feeds,queries_per_run=max(0,min(max_queries,12)),
            on_source=received)
        alerts=[];alert_health=[];custom=[];custom_health=[];keyed=[];keyed_health=[]
        if email_alerts.configured():
            monitor.phase('alerts','Reading subscribed LinkedIn / Bdjobs job-alert emails')
            alerts,alert_health=email_alerts.collect_email_alerts(sources,on_source=received,state=feed_state)
        if any(task['source_id'] in ('api:brave','api:jooble') for task in planned):
            monitor.phase('search','Querying licensed search / aggregator APIs')
            b_jobs,b_health,feed_state=search_apis.brave_search(session,feed_state,sources,
                per_run=int(os.environ.get('BRAVE_QUERIES_PER_RUN','2') or 2),on_source=received)
            j_jobs,j_health,feed_state=search_apis.jooble_search(session,feed_state,sources,
                per_run=int(os.environ.get('JOOBLE_QUERIES_PER_RUN','3') or 3),on_source=received)
            keyed=b_jobs+j_jobs; keyed_health=b_health+j_health
        if feeds_cfg:
            monitor.phase('custom','Checking your custom RSS / Google Alerts feeds')
            custom,custom_health,feed_state=custom_feeds.collect_custom_feeds(session,feeds_cfg,feed_state,sources,on_source=received)
        monitor.phase('employers','Checking Bangladesh bank, telecom and employer career pages')
        official,employer_health=coverage_round(
            sources,fetcher,max(0,min(max_career_pages,250)),
            detail_budget=max(0,min(max_detail_pages,600)), on_source=received)
        monitor.phase('ats','Checking employer-linked public recruitment APIs')
        # Plan only boards the ATS collector will actually process. Existing
        # rows keep their identity; newly discovered tasks expand the total.
        monitor.plan_sources([_ats_task(board) for board in configured_ats_boards(fetcher.discovered_ats)])
        ats,ats_health=ats_jobs(session,sources,fetcher.discovered_ats,on_source=received)
        health=remote_health+alert_health+keyed_health+custom_health+ats_health+employer_health
        new_candidates=validated(remote+alerts+keyed+custom+ats+official)
        # Preserve compatibility with batch-only collectors and guarantee
        # details even when optional callbacks aren't available.
        store.merge_batch(new_candidates)
        fresh_keys={similarity_key(j) for j in new_candidates}
        merged=annotate_freshness(store.jobs,int(os.environ.get('MAX_JOB_AGE_DAYS','45')))
        merged.sort(key=lambda j:(j.get('posted_at') or '0000-00-00',
                                  j.get('deadline') or '9999-99-99'),reverse=True)
        store.finish(merged)
        errors=[{'source':h.get('name','Unknown'),'state':h.get('state'),
                 'reason':h.get('reason_code') or h.get('message') or 'Unavailable'}
                for h in health if h.get('state') in ('error','failed','partial','limited','degraded')]
        if not dry_run:
            write_json(DATA/'feed_state.json',feed_state)
            persist_rejections()
            if fetcher.discovered_ats:
                seen={(x['provider'],x['board_token']):x for x in get_json(DATA/'ats_discovered.json',[])
                      if isinstance(x,dict) and x.get('provider') and x.get('board_token')}
                for board in fetcher.discovered_ats:seen[(board['provider'],board['board_token'])]=board
                write_json(DATA/'ats_discovered.json',list(seen.values()))
        monitor.finish()
        now=monitor.progress['finished_at']
        linkedin_jobs=[j for j in merged if 'linkedin' in (j.get('source','')+' '+j.get('source_url','')).lower()
                       or any('linkedin.com' in str(a.get('url','')) for a in j.get('also_listed_on',[]) if isinstance(a,dict))]
        capabilities={
            'directory_sources':len(sources),
            'eligible_employers':len(selected_employers(sources,250)),
            'scheduled_employers':len(selected_employers(sources,max(0,min(max_career_pages,250)))),
            'link_only_sources':sum(x.get('mode') in ('restricted','index','directory','link-only') or
                                    x.get('sector') in ('Job portal','Social media') for x in sources),
            'alert_mailbox_configured':email_alerts.configured(),
            'search_index_configured':bool(os.environ.get('BRAVE_API_KEY','').strip()),
            'aggregator_configured':bool(os.environ.get('JOOBLE_API_KEY','').strip()),
        }
        status={'updated_at':now,
                'engine':'Job Intelligence v5.2: vacancy evidence, source diagnostics, paginated discovery and durable completion times',
                'collection_started_at':monitor.progress['started_at'], 'collection_finished_at':now,
                'last_completed_at':monitor.progress['last_completed_at'],
                'last_successful_at':monitor.progress['last_successful_at'],
                'completion_status':monitor.progress['completion_status'],
                'duration_seconds':monitor.progress['duration_seconds'],
                'schedule':monitor.progress['schedule'],
                'refresh_interval_minutes':monitor.progress['schedule'].get('interval_minutes'),'no_paid_api':True,
                'queries_run':sum(int(x.get('requests',0)) for x in remote_health),
                'jobs_count':len(merged),
                'archived_expired':sum(j.get('vacancy_status')=='expired' for j in merged),
                'older_unverified':sum(j.get('vacancy_status')=='older_unverified' for j in merged),
                'bangladesh_jobs':sum(j.get('region','Bangladesh')=='Bangladesh' for j in merged),
                'international_jobs':sum(j.get('region')=='International' for j in merged),
                'new_candidates':len(new_candidates),
                'new_jobs_count':len(fresh_keys-previous_keys),
                'sources_in_directory':len(sources),
                'official_career_targets_checked':len(employer_health),
                'official_career_targets_reachable':sum(x['state']=='ok' for x in employer_health),
                'active_ats_boards':len(ats_health),'source_health':health,'errors':errors,
                'source_coverage':capabilities,
                'linkedin_coverage':{'listings_retained':len(linkedin_jobs),'complete':False,
                    'alerts_configured':capabilities['alert_mailbox_configured'],
                    'search_configured':capabilities['search_index_configured'],
                    'notice':'Coverage depends on subscribed job alerts and search indexing. LinkedIn alerts are daily or weekly; an hourly collector cannot guarantee all LinkedIn vacancies.'},
                'detection':{'version':'5.2','prior_records_checked':prior_count,
                    'prior_records_quarantined':previous_removed,'unique_records_rejected':len(rejected),
                    'note':'Rejected historical candidates are retained for local review, up to 1,000 records.'},
                'progress_summary':monitor.snapshot(),
                'collection_policy':'Hourly: employer pages (robots.txt honoured), public ATS APIs, free publisher feeds, your subscribed job-alert emails and optional licensed search/aggregator APIs. Restricted portals are never scraped directly.'}
        if not dry_run:
            write_json(DATA/'status.json',status)
        return status
    except Exception as exc:
        monitor.progress['last_completed_at']=prior_completion
        monitor.progress['last_successful_at']=prior_success
        monitor.finish(error=f'{type(exc).__name__}: collection interrupted')
        if not dry_run:
            failure={**previous_status, 'completion_status':'failed',
                     'jobs_count':len(store.jobs),
                     'last_completed_at':monitor.progress.get('last_completed_at'),
                     'last_successful_at':monitor.progress.get('last_successful_at'),
                     'collection_started_at':monitor.progress.get('started_at'),
                     'collection_finished_at':monitor.progress.get('finished_at'),
                     'progress_summary':monitor.snapshot(),
                     'last_attempt_error':f'{type(exc).__name__}: collection interrupted'}
            write_json(DATA/'status.json',failure)
        raise
    finally:
        try:
            persist_rejections()
        finally:
            session.close()


if __name__=='__main__':
    from server.app import load_local_env
    load_local_env()
    parser=argparse.ArgumentParser(description='Refresh CyberCareers BD without any paid API')
    parser.add_argument('--max-search-queries',type=int,default=int(os.getenv('MAX_FEED_SEARCHES','6')))
    parser.add_argument('--max-career-pages',type=int,default=int(os.getenv('MAX_CAREER_PAGES','250')))
    parser.add_argument('--max-detail-pages',type=int,default=int(os.getenv('MAX_DETAIL_PAGES','450')))
    parser.add_argument('--dry-run',action='store_true')
    parser.add_argument('--force-feeds',action='store_true',help='Ignore per-provider feed poll schedule for one diagnostic run')
    args=parser.parse_args()
    logging.basicConfig(level=logging.INFO,format='%(levelname)s %(message)s')
    print(json.dumps(run(args.max_search_queries,args.max_career_pages,args.max_detail_pages,args.dry_run,force_feeds=args.force_feeds),ensure_ascii=False,indent=2))
