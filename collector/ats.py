"""Public applicant-tracking-system (ATS) boards beyond Greenhouse/Lever/Ashby.

Every provider here exposes the same job data its public career site shows to
any visitor, without login. Board identities are only ever taken from links or
embeds that an employer actually publishes (or that you list in data/ats.json);
tokens are never guessed or brute-forced. Career-site style endpoints
(Workday, BambooHR, Breezy, Recruitee, Personio) are checked against that
host's robots.txt first.
"""
from __future__ import annotations

import html as _html
import logging
import os
import re
import threading
import time
from typing import Any, Callable
from urllib.parse import unquote, urlparse

import requests

LOG = logging.getLogger(__name__)
TIMEOUT = 15

# provider -> regex over raw page HTML (hrefs, iframes, script src, data attributes)
_DISCOVERY: dict[str, re.Pattern] = {
    'greenhouse': re.compile(r'(?<![A-Za-z0-9.-])(?:boards|job-boards)(?:\.eu)?\.greenhouse\.io/(?:embed/job_board(?:/js)?\?for=)?([A-Za-z0-9_-]{2,90})', re.I),
    'greenhouse_api': re.compile(r'(?<![A-Za-z0-9.-])boards-api\.greenhouse\.io/v1/boards/([A-Za-z0-9_-]{2,90})', re.I),
    'lever': re.compile(r'(?<![A-Za-z0-9.-])jobs\.lever\.co/([A-Za-z0-9_.-]{2,90})', re.I),
    'lever_eu': re.compile(r'(?<![A-Za-z0-9.-])jobs\.eu\.lever\.co/([A-Za-z0-9_.-]{2,90})', re.I),
    'ashby': re.compile(r'(?<![A-Za-z0-9.-])jobs\.ashbyhq\.com/([A-Za-z0-9_.%-]{2,90})', re.I),
    'workable': re.compile(r'(?<![A-Za-z0-9.-])apply\.workable\.com/([A-Za-z0-9_-]{2,90})', re.I),
    'workable_sub': re.compile(r'//([a-z0-9][a-z0-9-]{1,60})\.workable\.com', re.I),
    'smartrecruiters': re.compile(r'(?<![A-Za-z0-9.-])(?:jobs|careers)\.smartrecruiters\.com/([A-Za-z0-9_-]{2,90})', re.I),
    'recruitee': re.compile(r'//([a-z0-9][a-z0-9-]{1,60})\.recruitee\.com', re.I),
    'bamboohr': re.compile(r'//([a-z0-9][a-z0-9-]{1,60})\.bamboohr\.com', re.I),
    'personio': re.compile(r'//([a-z0-9][a-z0-9-]{1,60})\.jobs\.personio\.(de|com)', re.I),
    'breezy': re.compile(r'//([a-z0-9][a-z0-9-]{1,60})\.breezy\.hr', re.I),
    'workday': re.compile(r'//([a-z0-9][a-z0-9-]{1,60})\.(wd\d{1,3})\.myworkdayjobs\.com/(?:[a-z]{2}-[A-Z]{2}/)?([A-Za-z0-9_-]{2,90})', re.I),
}
_RESERVED = {'embed', 'api', 'v0', 'v1', 'jobs', 'job', 'j', 'www', 'apply', 'careers', 'search', 'static', 'assets',
             'login', 'signin', 'widget', 'widgets', 'js', 'help', 'support', 'privacy', 'terms', 'resources', 'blog', 'en-us', 'cdn'}
PROVIDERS = ('greenhouse', 'lever', 'lever_eu', 'ashby', 'workable', 'smartrecruiters', 'recruitee',
             'bamboohr', 'personio', 'breezy', 'workday')
TOKEN_RX = re.compile(r'[A-Za-z0-9_.|-]{2,160}')


class PostingBatch(list):
    """Postings plus honest coverage metadata when a public board is large."""
    def __init__(self, values=()):
        super().__init__(values)
        self.coverage_limited = False
        self.coverage_notes: list[str] = []

    def limited(self, note: str) -> None:
        self.coverage_limited = True
        if note not in self.coverage_notes:self.coverage_notes.append(note)


def _limit(name: str, default: int, maximum: int) -> int:
    try:return max(1,min(maximum,int(os.environ.get(name,str(default)) or default)))
    except ValueError:return default


def discover_boards(page_html: str, page_url: str, company: str) -> list[dict]:
    """Board identities published on an employer page (links, iframes, scripts)."""
    text = _html.unescape(page_html or '')
    boards: list[dict] = []

    def add(provider: str, token: str) -> None:
        token = unquote(token).strip().strip('.')
        if not TOKEN_RX.fullmatch(token) or token.split('|')[0].lower() in _RESERVED:
            return
        if not any(b['provider'] == provider and b['board_token'].lower() == token.lower() for b in boards):
            boards.append({'company': company, 'provider': provider, 'board_token': token,
                           'discovered_from': page_url})

    for key, rx in _DISCOVERY.items():
        for m in rx.finditer(text):
            if key == 'workday':
                add('workday', f'{m.group(1)}|{m.group(2)}|{m.group(3)}')
            elif key == 'personio':
                add('personio', m.group(1) if m.group(2).lower() == 'de' else f'{m.group(1)}|{m.group(2)}')
            elif key == 'greenhouse_api':
                add('greenhouse', m.group(1))
            elif key == 'workable_sub':
                add('workable', m.group(1))
            else:
                add(key, m.group(1))
    return boards


# --------------------------------------------------------------------------
# robots.txt for career-site style endpoints
# --------------------------------------------------------------------------
_ROBOTS: dict[str, Any] = {}
_ROBOTS_LOCK = threading.Lock()


def robots_ok(session: requests.Session, url: str, user_agent: str) -> bool:
    from .robots import ALLOW_ALL, RobotsPolicy
    parts = urlparse(url)
    key = f'{parts.scheme}://{parts.netloc}'
    with _ROBOTS_LOCK:
        policy = _ROBOTS.get(key)
    if policy is None:
        try:
            r = session.get(key + '/robots.txt', timeout=TIMEOUT, headers={'User-Agent': user_agent})
            code = getattr(r, 'status_code', 200)
            if 400 <= code < 500 and code != 429:
                policy = ALLOW_ALL
            elif 200 <= code < 300:
                policy = RobotsPolicy(r.text[:512_000])
            else:
                policy = False
        except requests.RequestException:
            policy = False
        with _ROBOTS_LOCK:
            _ROBOTS[key] = policy
    return bool(policy) and policy.can_fetch(user_agent, url)


# --------------------------------------------------------------------------
# Providers: each returns normalised postings
#   {title, url, apply_url, location, description, posted, employment_type, remote, department}
# --------------------------------------------------------------------------

def _get(session, url, ua, **kw):
    r = session.get(url, timeout=TIMEOUT, headers={'User-Agent': ua, 'Accept': 'application/json'}, **kw)
    r.raise_for_status()
    return r


def _workable(session, token, ua, wants):
    data = _get(session, f'https://apply.workable.com/api/v1/widget/accounts/{token}?details=true', ua).json()
    if not isinstance(data,dict) or not isinstance(data.get('jobs'),list):
        raise ValueError('Workable response did not contain a jobs array')
    out = []
    for j in data.get('jobs', []) if isinstance(data, dict) else []:
        locs = j.get('locations') or []
        loc_parts = [j.get('city'), j.get('state'), j.get('country')]
        if locs and isinstance(locs[0], dict):
            loc_parts = [locs[0].get('city'), locs[0].get('region'), locs[0].get('country')]
        out.append({'title': j.get('title'), 'url': j.get('url') or j.get('shortlink') or '',
                    'apply_url': j.get('application_url') or j.get('url') or '',
                    'location': ', '.join(str(x) for x in loc_parts if x),
                    'description': j.get('description') or '', 'posted': j.get('published_on') or j.get('created_at') or '',
                    'employment_type': j.get('employment_type') or '', 'remote': bool(j.get('telecommuting')),
                    'department': j.get('department') or ''})
    return out


def _smartrecruiters(session, token, ua, wants):
    out = PostingBatch()
    max_pages=_limit('ATS_MAX_PAGES',10,50)
    max_details=_limit('ATS_MAX_DETAILS',100,500)
    details=0;seen=set()
    for page in range(max_pages):
        offset=page*100
        data = _get(session, f'https://api.smartrecruiters.com/v1/companies/{token}/postings',
                    ua, params={'limit': 100, 'offset': offset}).json()
        if not isinstance(data,dict) or not isinstance(data.get('content'),list):
            raise ValueError('SmartRecruiters response did not contain a postings array')
        rows = data.get('content', []) if isinstance(data, dict) else []
        for j in rows:
            title = j.get('name') or ''
            if not wants(title):
                continue
            loc = j.get('location') or {}
            pid = j.get('id') or j.get('uuid') or ''
            if not pid or pid in seen:continue
            seen.add(pid)
            desc = ''
            if details<max_details:
                details+=1
                try:
                    detail = _get(session, f'https://api.smartrecruiters.com/v1/companies/{token}/postings/{pid}', ua).json()
                    sections = ((detail.get('jobAd') or {}).get('sections') or {})
                    desc = ' '.join((sections.get(k) or {}).get('text', '') for k in
                                    ('jobDescription', 'qualifications', 'additionalInformation', 'companyDescription'))
                except (requests.RequestException, ValueError):
                    out.limited('Some posting details could not be retrieved')
            else:
                out.limited('ATS_MAX_DETAILS reached; remaining postings retain public listing metadata')
            url = f'https://jobs.smartrecruiters.com/{token}/{pid}'
            out.append({'title': title, 'url': url, 'apply_url': url,
                        'location': loc.get('fullLocation') or ', '.join(str(loc[k]) for k in ('city', 'region', 'country') if loc.get(k)),
                        'description': desc, 'posted': j.get('releasedDate') or '',
                        'employment_type': (j.get('typeOfEmployment') or {}).get('label', ''),
                        'remote': bool(loc.get('remote')), 'department': (j.get('department') or {}).get('label', '')})
        total=data.get('totalFound') if isinstance(data,dict) else None
        if len(rows) < 100 or (total is not None and offset+len(rows)>=int(total)):
            break
        if page==max_pages-1:out.limited('ATS_MAX_PAGES reached before the board ended')
    return out


def _recruitee(session, token, ua, wants):
    url = f'https://{token}.recruitee.com/api/offers/'
    if not robots_ok(session, url, ua):
        raise PermissionError('robots.txt disallows the Recruitee board')
    data = _get(session, url, ua).json()
    if not isinstance(data,dict) or not isinstance(data.get('offers'),list):
        raise ValueError('Recruitee response did not contain an offers array')
    out = []
    for j in data.get('offers', []) if isinstance(data, dict) else []:
        out.append({'title': j.get('title'), 'url': j.get('careers_url') or '',
                    'apply_url': j.get('careers_apply_url') or j.get('careers_url') or '',
                    'location': j.get('location') or ', '.join(str(j[k]) for k in ('city', 'country') if j.get(k)),
                    'description': f"{j.get('description') or ''} {j.get('requirements') or ''}",
                    'posted': j.get('published_at') or j.get('created_at') or '',
                    'employment_type': j.get('employment_type_code') or '', 'remote': bool(j.get('remote')),
                    'department': j.get('department') or ''})
    return out


def _bamboohr(session, token, ua, wants):
    base = f'https://{token}.bamboohr.com/careers'
    if not robots_ok(session, base + '/list', ua):
        raise PermissionError('robots.txt disallows the BambooHR board')
    data = _get(session, base + '/list', ua).json()
    if not isinstance(data,dict) or not isinstance(data.get('result'),list):
        raise ValueError('BambooHR response did not contain a result array')
    out = []
    for j in data.get('result', []) if isinstance(data, dict) else []:
        title = j.get('jobOpeningName') or ''
        if not wants(title):
            continue
        loc = j.get('atsLocation') or j.get('location') or {}
        jid = j.get('id')
        desc = ''
        try:
            d = _get(session, f'{base}/{jid}/detail', ua).json()
            desc = ((d.get('result') or {}).get('jobOpening') or {}).get('description', '')
        except (requests.RequestException, ValueError, AttributeError):
            pass
        url = f'{base}/{jid}'
        out.append({'title': title, 'url': url, 'apply_url': url,
                    'location': ', '.join(str(loc[k]) for k in ('city', 'state', 'country') if isinstance(loc, dict) and loc.get(k)),
                    'description': desc, 'posted': j.get('datePosted') or '',
                    'employment_type': j.get('employmentStatusLabel') or '',
                    'remote': bool(j.get('isRemote')), 'department': j.get('departmentLabel') or ''})
    return out


def _personio(session, token, ua, wants):
    import xml.etree.ElementTree as ET
    tld = 'de'
    if '|' in token:
        token, tld = token.split('|', 1)
    url = f'https://{token}.jobs.personio.{tld}/xml'
    if not robots_ok(session, url, ua):
        raise PermissionError('robots.txt disallows the Personio feed')
    r = session.get(url, timeout=TIMEOUT, headers={'User-Agent': ua})
    r.raise_for_status()
    root = ET.fromstring(r.content)
    out = []
    for pos in root.iter('position'):
        g = lambda tag: (pos.findtext(tag) or '').strip()  # noqa: E731
        desc = ' '.join((d.findtext('value') or '') for d in pos.iter('jobDescription'))
        pid = g('id')
        link = f'https://{token}.jobs.personio.{tld}/job/{pid}'
        out.append({'title': g('name'), 'url': link, 'apply_url': link, 'location': g('office'),
                    'description': desc, 'posted': g('createdAt'), 'employment_type': g('schedule') or g('employmentType'),
                    'remote': 'remote' in g('office').lower(), 'department': g('department')})
    return out


def _breezy(session, token, ua, wants):
    url = f'https://{token}.breezy.hr/json'
    if not robots_ok(session, url, ua):
        raise PermissionError('robots.txt disallows the Breezy board')
    data = _get(session, url, ua).json()
    if not isinstance(data,list):
        raise ValueError('Breezy response did not contain a postings array')
    out = []
    for j in data if isinstance(data, list) else []:
        loc = j.get('location') or {}
        country = loc.get('country') or {}
        out.append({'title': j.get('name'), 'url': j.get('url') or '', 'apply_url': j.get('url') or '',
                    'location': loc.get('name') or ', '.join(x for x in (loc.get('city'), country.get('name') if isinstance(country, dict) else str(country)) if x),
                    'description': j.get('description') or '', 'posted': j.get('published_date') or '',
                    'employment_type': (j.get('type') or {}).get('name', '') if isinstance(j.get('type'), dict) else '',
                    'remote': bool(loc.get('is_remote')), 'department': j.get('department') or ''})
    return out


def _workday(session, token, ua, wants):
    tenant, wd, site = token.split('|', 2)
    host = f'https://{tenant}.{wd}.myworkdayjobs.com'
    api = f'{host}/wday/cxs/{tenant}/{site}'
    if not robots_ok(session, f'{host}/{site}', ua):
        raise PermissionError('robots.txt disallows the Workday career site')
    seen: dict[str, dict] = {}
    out=PostingBatch()
    max_pages=_limit('ATS_MAX_PAGES',10,50)
    max_details=_limit('ATS_MAX_DETAILS',100,500)
    for text in ('security', 'cyber', 'risk', 'audit'):
        for page in range(max_pages):
            offset=page*20
            r = session.post(api + '/jobs', timeout=TIMEOUT,
                             json={'appliedFacets': {}, 'limit': 20, 'offset': offset, 'searchText': text},
                             headers={'User-Agent': ua, 'Accept': 'application/json', 'Content-Type': 'application/json'})
            r.raise_for_status()
            data = r.json()
            if not isinstance(data,dict) or not isinstance(data.get('jobPostings'),list):
                raise ValueError('Workday response did not contain a postings array')
            rows = data.get('jobPostings', []) if isinstance(data, dict) else []
            for j in rows:
                path = j.get('externalPath') or ''
                if path and path not in seen and wants(j.get('title') or ''):
                    seen[path] = j
            total=data.get('total') if isinstance(data,dict) else None
            if len(rows) < 20 or (total is not None and offset+len(rows)>=int(total)):
                break
            if page==max_pages-1:out.limited('ATS_MAX_PAGES reached for one or more Workday search terms')
            time.sleep(0.3)
    for index,(path, j) in enumerate(seen.items()):
        desc, loc, posted = '', j.get('locationsText') or '', j.get('postedOn') or ''
        if index<max_details:
            try:
                info = _get(session, api + path, ua).json().get('jobPostingInfo', {})
                desc = info.get('jobDescription') or ''
                loc = ', '.join(x for x in (info.get('location'), (info.get('country') or {}).get('descriptor')) if x) or loc
                posted = info.get('startDate') or posted
            except (requests.RequestException, ValueError, AttributeError):
                out.limited('Some posting details could not be retrieved')
        else:
            out.limited('ATS_MAX_DETAILS reached; remaining postings retain public listing metadata')
        url = f'{host}/{site}{path}'
        out.append({'title': j.get('title'), 'url': url, 'apply_url': url, 'location': loc, 'description': desc,
                    'posted': posted if re.match(r'\d{4}-\d{2}-\d{2}', str(posted)) else '',
                    'employment_type': '', 'remote': 'remote' in loc.lower(), 'department': ''})
    return out


FETCHERS: dict[str, Callable] = {
    'workable': _workable, 'smartrecruiters': _smartrecruiters, 'recruitee': _recruitee,
    'bamboohr': _bamboohr, 'personio': _personio, 'breezy': _breezy, 'workday': _workday,
}
SOURCE_LABEL = {
    'workable': 'Workable public API', 'smartrecruiters': 'SmartRecruiters public API',
    'recruitee': 'Recruitee public API', 'bamboohr': 'BambooHR careers', 'personio': 'Personio XML feed',
    'breezy': 'Breezy HR public feed', 'workday': 'Workday career site',
}


def fetch_board(session: requests.Session, provider: str, token: str, ua: str, wants: Callable[[str], bool]) -> list[dict]:
    return FETCHERS[provider](session, token, ua, wants)
