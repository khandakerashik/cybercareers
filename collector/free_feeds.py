"""Key-free international job data providers with conservative country confidence.

The portal refreshes every hour, but published provider data is polled only at
its documented cadence. We preserve ambiguous worldwide eligibility as
*unconfirmed* instead of silently deleting otherwise relevant opportunities.
"""
from __future__ import annotations

import logging
import re
import time
from datetime import datetime, timezone
from typing import Any
from urllib.parse import urlparse

import requests

LOG = logging.getLogger(__name__)
PROVIDERS = {
    'Himalayas': {'seconds': 24 * 3600, 'url': 'https://himalayas.app/jobs/api/search'},
    'Remotive': {'seconds': 6 * 3600, 'url': 'https://remotive.com/api/remote-jobs'},
    'Remote OK': {'seconds': 3 * 3600, 'url': 'https://remoteok.com/api'},
    'Jobicy': {'seconds': 3600, 'url': 'https://jobicy.com/api/jobs'},
    'We Work Remotely': {'seconds': 3 * 3600, 'url': 'https://weworkremotely.com/remote-jobs.rss',
                         'extra': ['https://weworkremotely.com/categories/remote-devops-sysadmin-jobs.rss']},
    'Working Nomads': {'seconds': 6 * 3600, 'url': 'https://www.workingnomads.com/api/exposed_jobs/'},
}
BD_COUNTRY_CODES = {'BD', 'BGD', 'BANGLADESH'}
CONFIRMED = 'confirmed'
REGIONAL = 'regional'
UNCONFIRMED = 'unconfirmed'


def unix_to_iso(value: Any) -> str:
    try:
        number = float(value)
        if number > 1e11:
            number /= 1000
        return datetime.fromtimestamp(number, timezone.utc).date().isoformat()
    except (ValueError, TypeError, OverflowError, OSError):
        return ''


def country_is_bd(entry: Any) -> bool:
    if isinstance(entry, dict):
        possible = [entry.get(k, '') for k in ('alpha2', 'alpha3', 'countryCode', 'code', 'name', 'country')]
    elif isinstance(entry, str):
        possible = [entry]
    else:
        return False
    return any(str(x).strip().upper() in BD_COUNTRY_CODES for x in possible)


def bd_timezone_allowed(value: Any) -> bool:
    """Publisher APIs may use numeric UTC offsets, not just 'UTC+06:00'."""
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        # API stores hours; do not assume an offset in seconds.
        return abs(float(value) - 6) < 0.001 or abs(float(value) - 360) < 0.001
    normalized = re.sub(r'\s+', '', str(value or '').lower())
    if normalized in ('worldwide', 'any', 'all', '+6', '+06', '+0600', '+06:00', '6', '360'):
        return True
    return bool(re.fullmatch(r'(?:utc|gmt)\+0?6(?::?00)?', normalized))


def _timezone_check(tz: Any) -> str:
    if not isinstance(tz, list) or not tz:
        return 'ok'
    if any(bd_timezone_allowed(x) for x in tz):
        return 'ok'
    if any('worldwide' in str(x).lower() for x in tz):
        return 'ok'
    # Known numeric disallow-list -> BD UTC+6 is definitively absent.
    if all(isinstance(x, (int, float)) or re.fullmatch(r'(?:UTC|GMT)?[+-]\d{1,2}(?::?00)?', str(x).strip(), re.I) for x in tz):
        return 'excluded'
    return 'uncertain'


def eligible_location(restrictions: Any, tz: Any, *, allow_unknown: bool = False) -> str | None:
    """Only confirm Bangladesh eligibility when the feed explicitly establishes it."""
    if restrictions is None or not isinstance(restrictions, list):
        return 'Location not specified — verify Bangladesh eligibility' if allow_unknown else None
    checked_tz = _timezone_check(tz)
    if checked_tz == 'excluded':
        return None
    if restrictions:
        if any(country_is_bd(x) for x in restrictions):
            result = 'Bangladesh eligible'
        elif any(re.search(r'\b(worldwide|anywhere|global)\b', str(x), re.I) for x in restrictions):
            result = 'Worldwide listed — verify employer conditions'
        elif any(re.search(r'\b(apac|asia|south asia)\b', str(x), re.I) for x in restrictions):
            result = 'Regional (Asia/APAC) — verify Bangladesh eligibility'
        else:
            return None
    else:
        result = 'Worldwide / Bangladesh eligible'
    if checked_tz == 'uncertain':
        return 'Timezone restricted — verify Bangladesh eligibility' if allow_unknown else None
    return result


def text_location_eligibility(raw: str, *, allow_unknown: bool = False) -> str | None:
    value = str(raw or '').strip()
    low = value.lower()
    if re.search(r'\b(except|excluding|not available in)\s+(?:bangladesh|bd)\b', low):
        return None
    if re.search(r'\b(?:us|usa|u\.?s\.?a\.?|united states|uk|united kingdom|canada|india|europe|australia)\s+(?:only|residents only)\b', low):
        return None
    if re.search(r'\bonly\s+(?:in|for)\s+(?:the\s+)?(?:united states|usa|us|uk|canada|india|europe|australia)\b', low):
        return None
    # 'Anywhere in the US' does not mean worldwide.  Interpret the scope first.
    if re.search(r'\banywhere\s+(?:within|in|across)\s+(?:the\s+)?(?:us|u\.?s\.?a\.?|united states|uk|united kingdom|canada|india|europe|australia)\b', low):
        return None
    if re.search(r'\b(bangladesh|dhaka)\b', low):
        return 'Bangladesh eligible'
    if re.search(r'\b(worldwide|world wide|anywhere in the world|work from anywhere|globally|global|anywhere)\b', low):
        return 'Worldwide listed — verify employer conditions'
    if re.search(r'\b(apac|asia.pacific|south asia|asia)\b', low):
        return 'Regional (Asia/APAC) — verify Bangladesh eligibility'
    if not value or re.fullmatch(r'(remote|work from home|flexible|distributed|virtual)(\s*(\(.+\))?)?', value, re.I):
        return 'Location not specified — verify Bangladesh eligibility' if allow_unknown else None
    # A named overseas country is *not* a Bangladesh opportunity.
    return None


def confidence(eligibility: str) -> str:
    if eligibility.startswith(('Worldwide', 'Bangladesh')):
        return CONFIRMED
    return REGIONAL if eligibility.startswith('Regional') else UNCONFIRMED


def salary_himalayas(item: dict) -> str:
    low, high = item.get('minSalary'), item.get('maxSalary')
    if low is None and high is None:
        return 'Not disclosed'
    def money(val: Any) -> str:
        try:
            return f'{float(val):,.0f}'
        except (ValueError, TypeError):
            return str(val)
    amount = f'{money(low)}–{money(high)}' if low is not None and high is not None else money(low if low is not None else high)
    return f"{item.get('currency') or ''} {amount} / {item.get('salaryPeriod') or 'annual'}".strip()


def _complete_job(*, title: str, desc: str, apply_url: str, source_url: str, company: str, source: str, sources: list[dict],
                  eligibility: str, **kwargs: Any) -> dict:
    from .collect import new_job, find_skills
    return new_job(title=title, company=company or 'Employer not identified', url=source_url,
                   apply_url=apply_url, source=source, sources=sources, description=desc,
                   skills=find_skills(title + ' ' + desc), location=kwargs.pop('location', 'Remote — verify eligibility'),
                   workplace='Remote', region='International', eligibility=eligibility,
                   eligibility_confidence=confidence(eligibility),
                   verification_level='Publisher public API',
                   description_status='Full feed description' if len(desc) > 200 else 'Publisher excerpt',
                   company_sector='International employer', **kwargs)


def parse_himalayas(payload: dict, sources: list[dict]) -> list[dict]:
    from .collect import clean_text, is_relevant, valid_url
    output = []
    for item in payload.get('jobs', []) if isinstance(payload, dict) else []:
        if not isinstance(item, dict):
            continue
        title = clean_text(item.get('title'), 200)
        desc = clean_text(item.get('description') or item.get('excerpt'), 11000)
        if not is_relevant(title, desc):
            continue
        eligibility = eligible_location(item.get('locationRestrictions'), item.get('timezoneRestrictions'), allow_unknown=True)
        if not eligibility:
            continue
        apply_url = item.get('applicationLink') or ''
        if not valid_url(apply_url):
            continue
        guid = item.get('guid') or ''
        domain = urlparse(guid).hostname or ''
        source_url = guid if valid_url(guid) and (domain == 'himalayas.app' or domain.endswith('.himalayas.app')) else apply_url
        logo = item.get('companyLogo') or ''
        if not valid_url(logo):
            logo = ''
        output.append(_complete_job(title=title, desc=desc, apply_url=apply_url, source_url=source_url,
            company=item.get('companyName'), source='Himalayas', sources=sources,
            eligibility=eligibility, posted=item.get('pubDate') and unix_to_iso(item['pubDate']),
            deadline=item.get('expiryDate') and unix_to_iso(item['expiryDate']),
            location='Worldwide (remote)' if confidence(eligibility) == CONFIRMED else 'Remote — eligibility requires review',
            employment_type=item.get('employmentType') or 'Not specified',
            seniority=item.get('seniority') or 'Not specified',
            salary=salary_himalayas(item), company_logo_url=logo))
    return output


def parse_remotive(payload: dict, sources: list[dict]) -> list[dict]:
    from .collect import clean_text, is_relevant, valid_url
    output = []
    for item in payload.get('jobs', []) if isinstance(payload, dict) else []:
        if not isinstance(item, dict):
            continue
        title = clean_text(item.get('title'), 200)
        desc = clean_text(item.get('description'), 11000)
        if not is_relevant(title, desc):
            continue
        eligibility = text_location_eligibility(item.get('candidate_required_location', ''), allow_unknown=True)
        if not eligibility:
            continue
        url = item.get('url') or ''
        if not valid_url(url):
            continue
        logo = item.get('company_logo') or ''
        output.append(_complete_job(title=title, desc=desc, apply_url=url, source_url=url,
            company=item.get('company_name'), source='Remotive', sources=sources, eligibility=eligibility,
            posted=item.get('publication_date'), location=item.get('candidate_required_location') or 'Remote — eligibility requires review',
            employment_type=item.get('job_type') or 'Not specified', salary=item.get('salary') or 'Not disclosed',
            company_logo_url=logo if valid_url(logo) else ''))
    return output


def parse_remoteok(payload: list, sources: list[dict]) -> list[dict]:
    from .collect import clean_text, is_relevant, valid_url
    output = []
    for item in payload if isinstance(payload, list) else []:
        if not isinstance(item, dict):
            continue
        title = clean_text(item.get('position') or item.get('title'), 200)
        desc = clean_text(item.get('description'), 11000)
        if not is_relevant(title, desc):
            continue
        eligibility = text_location_eligibility(item.get('location') or '', allow_unknown=True)
        if not eligibility:
            continue
        url = item.get('url') or item.get('apply_url') or ''
        if not valid_url(url):
            continue
        logo = item.get('company_logo') or item.get('logo') or ''
        low, high = item.get('salary_min'), item.get('salary_max')
        salary = item.get('salary') or 'Not disclosed'
        if salary == 'Not disclosed' and (low or high):
            try:
                salary = 'USD ' + '–'.join(f'{int(n):,}' for n in (low, high) if n)
            except (ValueError, TypeError):
                pass
        output.append(_complete_job(title=title, desc=desc, apply_url=url, source_url=url,
            company=item.get('company'), source='Remote OK', sources=sources, eligibility=eligibility,
            posted=unix_to_iso(item.get('epoch')) or item.get('date'),
            location=item.get('location') or 'Remote — eligibility requires review',
            salary=salary, company_logo_url=logo if valid_url(logo) else ''))
    return output


def parse_jobicy(payload: dict, sources: list[dict]) -> list[dict]:
    from .collect import clean_text, is_relevant, valid_url
    output = []
    for item in payload.get('jobs', []) if isinstance(payload, dict) else []:
        if not isinstance(item, dict):
            continue
        title = clean_text(item.get('jobTitle'), 200)
        desc = clean_text(item.get('jobDescription') or item.get('jobExcerpt'), 11000)
        if not is_relevant(title, desc):
            continue
        eligibility = text_location_eligibility(item.get('jobGeo', ''), allow_unknown=True)
        if not eligibility:
            continue
        url = item.get('url') or ''
        host = urlparse(url).hostname or ''
        if not valid_url(url) or not (host == 'jobicy.com' or host.endswith('.jobicy.com')):
            continue
        logo = item.get('companyLogo') or ''
        low, high = item.get('salaryMin'), item.get('salaryMax')
        salary = 'Not disclosed'
        if low is not None or high is not None:
            try:
                amount = '–'.join(f'{float(n):,.0f}' for n in (low, high) if n is not None)
                salary = f"{item.get('salaryCurrency') or ''} {amount} / {item.get('salaryPeriod') or 'year'}".strip()
            except (ValueError, TypeError):
                pass
        types = item.get('jobType') or []
        output.append(_complete_job(title=title, desc=desc, apply_url=url, source_url=url,
            company=item.get('companyName'), source='Jobicy', sources=sources, eligibility=eligibility,
            posted=item.get('pubDate'), location=item.get('jobGeo') or 'Remote — eligibility requires review',
            employment_type=', '.join(types) if isinstance(types, list) else str(types),
            seniority=item.get('jobLevel') or 'Not specified', salary=salary,
            company_logo_url=logo if valid_url(logo) else ''))
    return output


def parse_wwr(xml_text: str | bytes, sources: list[dict]) -> list[dict]:
    """We Work Remotely RSS: <title>Company: Role</title>, <region>, <link>, <description>."""
    import xml.etree.ElementTree as ET
    from .collect import clean_text, is_relevant, valid_url
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError:
        return []
    output = []
    for item in root.iter('item'):
        raw_title = clean_text(item.findtext('title'), 240)
        company, _, title = raw_title.partition(': ')
        if not title:
            company, title = '', raw_title
        desc = clean_text(item.findtext('description'), 11000)
        if not is_relevant(title, desc):
            continue
        region = clean_text(item.findtext('region'), 200)
        eligibility = text_location_eligibility(region, allow_unknown=True)
        if not eligibility:
            continue
        url = (item.findtext('link') or item.findtext('guid') or '').strip()
        if not valid_url(url) or not (urlparse(url).hostname or '').endswith('weworkremotely.com'):
            continue
        output.append(_complete_job(title=title, desc=desc, apply_url=url, source_url=url, company=company,
            source='We Work Remotely', sources=sources, eligibility=eligibility, posted=item.findtext('pubDate') or '',
            location=region or 'Remote — eligibility requires review',
            employment_type=clean_text(item.findtext('type'), 60) or 'Not specified'))
    return output


def parse_working_nomads(payload: list, sources: list[dict]) -> list[dict]:
    from .collect import clean_text, is_relevant, valid_url
    output = []
    for item in payload if isinstance(payload, list) else []:
        if not isinstance(item, dict):
            continue
        title = clean_text(item.get('title'), 200)
        desc = clean_text(item.get('description'), 11000)
        if not is_relevant(title, desc):
            continue
        eligibility = text_location_eligibility(item.get('location') or '', allow_unknown=True)
        if not eligibility:
            continue
        url = item.get('url') or ''
        if not valid_url(url):
            continue
        output.append(_complete_job(title=title, desc=desc, apply_url=url, source_url=url,
            company=item.get('company_name'), source='Working Nomads', sources=sources, eligibility=eligibility,
            posted=item.get('pub_date') or '', location=item.get('location') or 'Remote — eligibility requires review'))
    return output


def _received(name: str, response: Any) -> int:
    return len(response.get('jobs', [])) if isinstance(response, dict) and name != 'Remote OK' else len(response) if isinstance(response, list) else 0


def _request(session: requests.Session, url: str, **kwargs: Any) -> dict | list:
    response = session.get(url, timeout=22, **kwargs)
    response.raise_for_status()
    data = response.json()
    if not isinstance(data, (dict, list)):
        raise ValueError('Unexpected provider payload type')
    if isinstance(data, dict) and data.get('success') is False:
        raise ValueError('Provider API reported failure')
    return data


def _safe_error(exc: Exception) -> str:
    status = getattr(getattr(exc, 'response', None), 'status_code', None)
    if status:
        return f'HTTP {status}'
    if isinstance(exc, requests.Timeout):
        return 'Network timeout'
    if isinstance(exc, requests.ConnectionError):
        return 'Cannot connect to provider (network or DNS)'
    return 'Invalid response or provider unavailable'


def collect_public_feeds(session: requests.Session, sources: list[dict], cache: dict, *, force: bool = False,
                         queries_per_run: int = 5, clock: float | None = None, on_source=None) -> tuple[list[dict], list[dict], dict]:
    """One scheduled scan, per-provider query budgets, with raw/kept diagnostics.

    The Himalayas API is cached for 24h. The query rotation uses a saved search
    index instead of the current hour, so it never repeats the same 5 terms each
    day on an hourly scheduler started at the same clock hour.
    """
    clock = time.time() if clock is None else clock
    statuses: list[dict] = []
    found: list[dict] = []
    state = dict(cache) if isinstance(cache, dict) else {}
    for name, spec in PROVIDERS.items():
        batch_start = len(found)
        previous = state.get(name, {}) if isinstance(state.get(name), dict) else {}
        due = clock >= float(previous.get('next_check', 0))
        if not due and not force:
            outcome={'name': name, 'source_id': 'feed:'+name, 'sector': 'Remote job feed', 'state': 'cached', 'jobs_found': 0,
                'raw_jobs': previous.get('last_raw_jobs', 0), 'last_found': previous.get('jobs_found', 0),
                'requests': 0, 'mode': 'Free publisher feed',
                'next_check': datetime.fromtimestamp(float(previous['next_check']), timezone.utc).isoformat(timespec='minutes'),
                'last_error': previous.get('last_error', '')}
            statuses.append(outcome)
            if on_source: on_source(outcome,[])
            continue
        count = 0
        raw_jobs = 0
        requests_count = 0
        errors: list[str] = []
        try:
            if name == 'Himalayas':
                # Expand beyond narrow country=BD; worldwide=true returns global
                # hires and BD search finds country-specific hires. The server
                # continues to verify location restrictions inside each result.
                terms = ['security', 'information security', 'cybersecurity', 'security engineer',
                         'application security', 'SOC analyst', 'penetration testing', 'cloud security',
                         'DevSecOps', 'security governance', 'threat intelligence', 'CISO',
                         'information security manager', 'security audit', 'security analyst', 'GRC',
                         'সাইবার নিরাপত্তা', 'তথ্য নিরাপত্তা', 'সাইবার সিকিউরিটি', 'আইটি সিকিউরিটি']
                offset = int(previous.get('term_index', 0)) % len(terms)
                size = max(1, min(int(queries_per_run or 5), 8))
                selected = [terms[(offset + i) % len(terms)] for i in range(size)]
                for term in selected:
                    # Two searches are meaningful: worldwide (without country
                    # restriction) and explicit BD. Neither route needs a key.
                    for geo in ({'worldwide': 'true'}, {'country': 'BD'}):
                        # Himalayas search pages hold 20 results. A second page
                        # captures high-volume terms without an unbounded crawl.
                        for page in (1, 2):
                            payload = _request(session, spec['url'], params={
                                'q': term, 'sort': 'recent', 'page': page, **geo})
                            requests_count += 1
                            received = _received(name, payload)
                            raw_jobs += received
                            parsed = parse_himalayas(payload, sources)
                            found.extend(parsed)
                            count += len(parsed)
                            if received < 20:
                                break
                state[name] = {'term_index': (offset + size) % len(terms)}
            elif name == 'Remotive':
                payload = _request(session, spec['url'])
                requests_count += 1
                raw_jobs += _received(name, payload)
                parsed = parse_remotive(payload, sources)
                found.extend(parsed)
                count += len(parsed)
            elif name == 'Jobicy':
                # Tag filter searches content, rather than just category.
                for term in ('cybersecurity', 'information security', 'security'):
                    payload = _request(session, spec['url'], params={'count': 200, 'tag': term},
                                       headers={'Accept': 'application/json'})
                    requests_count += 1
                    raw_jobs += _received(name, payload)
                    parsed = parse_jobicy(payload, sources)
                    found.extend(parsed)
                    count += len(parsed)
                    # Fetch a second page only if there are many matches and
                    # there is a real cursor. Cursors are opaque, as specified.
                    cursor = payload.get('nextCursor') if isinstance(payload, dict) else None
                    if cursor and isinstance(cursor, str) and raw_jobs < 800:
                        extra = _request(session, spec['url'], params={'count': 200, 'tag': term, 'cursor': cursor},
                                         headers={'Accept': 'application/json'})
                        requests_count += 1
                        raw_jobs += _received(name, extra)
                        extra_jobs = parse_jobicy(extra, sources)
                        found.extend(extra_jobs)
                        count += len(extra_jobs)
            elif name == 'We Work Remotely':
                for feed_url in [spec['url'], *spec.get('extra', [])]:
                    response = session.get(feed_url, timeout=22, headers={'Accept': 'application/rss+xml, application/xml'})
                    response.raise_for_status()
                    requests_count += 1
                    body = getattr(response, 'content', b'') or b''
                    raw_jobs += body.count(b'<item>') if isinstance(body, bytes) else 0
                    parsed = parse_wwr(body, sources)
                    found.extend(parsed)
                    count += len(parsed)
            elif name == 'Working Nomads':
                payload = _request(session, spec['url'], headers={'Accept': 'application/json'})
                requests_count += 1
                raw_jobs += len(payload) if isinstance(payload, list) else 0
                parsed = parse_working_nomads(payload, sources)
                found.extend(parsed)
                count += len(parsed)
            else:
                payload = _request(session, spec['url'], headers={'Accept': 'application/json'})
                requests_count += 1
                raw_jobs += _received(name, payload)
                parsed = parse_remoteok(payload, sources)
                found.extend(parsed)
                count += len(parsed)
            state[name] = {**state.get(name, {}), 'checked_at': clock,
                           'next_check': clock + spec['seconds'], 'last_success': clock,
                           'jobs_found': count, 'last_raw_jobs': raw_jobs,
                           'requests_count': requests_count, 'last_error': ''}
            outcome={'name': name, 'source_id': 'feed:'+name, 'sector': 'Remote job feed', 'state': 'ok', 'jobs_found': count,
                'raw_jobs': raw_jobs, 'requests': requests_count, 'mode': 'Free publisher feed',
                'message': f'{count} cybersecurity candidates from {raw_jobs} raw records'}
            statuses.append(outcome)
            if on_source: on_source(outcome,found[batch_start:])
        except (requests.RequestException, ValueError, TypeError, KeyError) as exc:
            detail = _safe_error(exc)
            LOG.warning('%s feed failed after %s requests: %s', name, requests_count, detail)
            code = getattr(getattr(exc, 'response', None), 'status_code', None)
            next_in = spec['seconds'] if code in (401, 403, 429) else 3600
            state[name] = {**previous, 'next_check': clock + next_in,
                           'last_error': detail, 'checked_at': clock,
                           'requests_count': requests_count, 'last_raw_jobs': raw_jobs}
            outcome={'name': name, 'source_id': 'feed:'+name, 'sector': 'Remote job feed', 'state': 'error', 'jobs_found': count,
                'raw_jobs': raw_jobs, 'requests': requests_count,
                'mode': 'Free publisher feed', 'message': detail}
            statuses.append(outcome)
            if on_source: on_source(outcome,found[batch_start:])
    return found, statuses, state
