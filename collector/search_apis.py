"""Bounded, paginated discovery via licensed search and job aggregator APIs.

The portals themselves are never fetched. A search index and subscribed alerts
cannot guarantee every LinkedIn posting. Coverage, page limits and request
budgets are reported explicitly. API plans/quotas must be checked with providers.
"""
from __future__ import annotations

import os
import re
import time
from datetime import datetime, timezone
from urllib.parse import urlparse

import requests

BRAVE_QUERIES = [
    'site:linkedin.com/jobs/view "information security" Bangladesh',
    'site:linkedin.com/jobs/view "cyber security" Bangladesh',
    'site:linkedin.com/jobs/view "cybersecurity" Bangladesh',
    'site:linkedin.com/jobs/view "SOC analyst" Bangladesh',
    'site:linkedin.com/jobs/view "security engineer" Bangladesh',
    'site:linkedin.com/jobs/view "penetration" Bangladesh',
    'site:linkedin.com/jobs/view "application security" Bangladesh',
    'site:linkedin.com/jobs/view "network security" Bangladesh',
    'site:linkedin.com/jobs/view "IT audit" Bangladesh',
    'site:linkedin.com/jobs/view "GRC" Bangladesh',
    'site:linkedin.com/jobs/view "DevSecOps" Bangladesh',
    'site:linkedin.com/jobs/view "cloud security" Bangladesh',
    'site:linkedin.com/jobs/view "CISO" Bangladesh',
    'site:linkedin.com/jobs/view "security" Dhaka',
    'site:linkedin.com/jobs/view "threat" Bangladesh',
    'site:linkedin.com/jobs/view "identity" Bangladesh',
    'site:linkedin.com/jobs/view "security" "APAC" "remote"',
    'site:linkedin.com/jobs/view "security" "worldwide" "remote"',
    'site:bdjobs.com "information security"',
    'site:bdjobs.com "cyber security"',
    'site:bdjobs.com "IT audit"',
    'site:bdjobs.com "SOC"',
    '"information security" job circular bank Bangladesh',
    'সাইবার নিরাপত্তা নিয়োগ বিজ্ঞপ্তি',
    'তথ্য নিরাপত্তা কর্মকর্তা নিয়োগ',
    '"cyber security" vacancy Dhaka apply',
]
JOOBLE_KEYWORDS = ['information security', 'cyber security', 'security engineer', 'SOC analyst',
                   'penetration testing', 'IT audit', 'network security', 'security analyst', 'GRC',
                   'DevSecOps', 'application security', 'cloud security']


def _integer(name: str, default: int, low: int = 1, high: int = 100000) -> int:
    try:
        return min(high, max(low, int(os.environ.get(name, str(default)).strip())))
    except (TypeError, ValueError):
        return default


def _number(value, default=0):
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _cooldown(exc, clock):
    response = getattr(exc, 'response', None)
    code = getattr(response, 'status_code', None)
    # Do not retry immediately on a plan or provider-wide failure.
    seconds = 3600 if code == 429 else 900
    if response is not None:
        seconds = max(seconds, min(86400, _number(response.headers.get('Retry-After'), 0)))
    return code, clock + seconds


def _finish(name: str, state: dict, st: dict, jobs: dict, outcome: dict, on_source):
    state = {**state, name: st}
    found = list(jobs.values())
    outcome['jobs_found'] = len(found)
    if on_source:
        on_source(outcome, found)
    return found, [outcome], state


def _job_key(job: dict):
    from .email_alerts import canonical_portal_job
    url = job.get('source_url') or job.get('apply_url') or ''
    canonical = canonical_portal_job(url)
    return canonical[1] if canonical else url


def brave_search(session: requests.Session, state: dict, sources: list[dict], *, per_run: int = 2,
                 on_source=None) -> tuple[list[dict], list[dict], dict]:
    from .collect import indexed_result_to_job
    from .telemetry import source_started
    key = os.environ.get('BRAVE_API_KEY', '').strip()
    if not key:
        return [], [], state
    if per_run <= 0:
        outcome={'name':'Brave Search API','source_id':'api:brave','sector':'Search API','mode':'Licensed search index',
                 'state':'skipped','jobs_found':0,'message':'Disabled by the configured per-run query budget'}
        if on_source:on_source(outcome,[])
        return [],[outcome],state
    st = dict(state.get('brave') or {})
    clock = time.time()
    month = datetime.fromtimestamp(clock, timezone.utc).strftime('%Y-%m')
    if st.get('request_month') != month:
        st.update(request_month=month, monthly_requests=0)
    monthly_limit = _integer('BRAVE_MONTHLY_REQUEST_LIMIT', 1500, 0)
    per_run_limit = _integer('BRAVE_MAX_REQUESTS_PER_RUN', 2, 1, 100)
    page_limit = _integer('BRAVE_PAGES_PER_QUERY', 2, 1, 10)
    used = _number(st.get('monthly_requests'))
    remaining = min(per_run_limit, max(0, monthly_limit - used))
    jobs = {}
    outcome = {'name': 'Brave Search API', 'source_id': 'api:brave', 'sector': 'Search API',
               'mode': 'Licensed search index', 'coverage': 'Indexed postings only; not all LinkedIn jobs',
               'query_pool_size': len(BRAVE_QUERIES), 'page_limit': page_limit,
               'monthly_request_limit': monthly_limit}
    if clock < float(st.get('next_check') or 0) or remaining <= 0:
        outcome.update(state='cached', message='Provider cooldown or configured monthly request budget reached',
                       requests_used=0, monthly_requests=used, coverage_limited=True)
        return _finish('brave', state, st, jobs, outcome, on_source)
    source_started(on_source, outcome)
    start = _number(st.get('index')) % len(BRAVE_QUERIES)
    queries = [BRAVE_QUERIES[(start+i) % len(BRAVE_QUERIES)] for i in range(min(per_run, len(BRAVE_QUERIES)))]
    cursors = dict(st.get('page_cursors') or {})
    attempts = successes = raw = started = completed = truncated = 0
    errors = []
    stop = False
    for q in queries:
        query_allowance = max(1, (remaining - attempts) // max(1, len(queries) - started))
        query_attempts = 0
        if attempts >= remaining or stop:
            break
        started += 1
        page = min(page_limit-1, max(0, _number(cursors.get(q))))
        page_urls = set()
        while page < page_limit and attempts < remaining and query_attempts < query_allowance:
            if attempts:
                time.sleep(1.1)
            params = {'q': q, 'count': 20, 'offset': page, 'extra_snippets': True, 'safesearch': 'moderate'}
            # An obligatory 31-day filter misses open vacancies with older/unknown index dates.
            freshness = os.environ.get('BRAVE_FRESHNESS', '').strip()
            if freshness:
                params['freshness'] = freshness
            attempts += 1
            query_attempts += 1
            used += 1
            try:
                response = session.get('https://api.search.brave.com/res/v1/web/search', timeout=20, allow_redirects=False,
                                       params=params, headers={'Accept': 'application/json', 'X-Subscription-Token': key})
                response.raise_for_status()
                if 300 <= response.status_code < 400:
                    raise ValueError('Unexpected redirect from search API')
                payload = response.json()
                if not isinstance(payload, dict) or payload.get('error') or not isinstance(payload.get('web') or {}, dict):
                    raise ValueError('Invalid search payload')
                results = (payload.get('web') or {}).get('results') or []
                if not isinstance(results, list):
                    raise ValueError('Invalid search results')
                successes += 1
                raw += len(results)
                urls = {x.get('url') for x in results if isinstance(x, dict) and isinstance(x.get('url'), str)}
                new_urls = urls - page_urls
                page_urls |= urls
                for item in results:
                    if not isinstance(item, dict):
                        continue
                    try:
                        job = indexed_result_to_job(item, sources)
                    except (ValueError, TypeError, KeyError):
                        continue
                    if job:
                        jobs[_job_key(job)] = job
                query_info = payload.get('query') or {}
                more = query_info.get('more_results_available') if isinstance(query_info, dict) else None
                if results and not new_urls and more is not False:
                    truncated += 1  # Repeated pages do not prove the index is exhausted.
                if not results or not new_urls or more is False:
                    cursors.pop(q, None)
                    completed += 1
                    break
                page += 1
                if page >= page_limit:
                    truncated += 1
                    cursors.pop(q, None)
                else:
                    cursors[q] = page
            except (requests.RequestException, ValueError, TypeError) as exc:
                code, retry_at = _cooldown(exc, clock)
                errors.append(f'HTTP {code}' if code else type(exc).__name__)
                cursors[q] = page
                if code in (401, 403, 429):
                    st['next_check'] = retry_at
                    stop = True
                break
    st.update(index=(start+started) % len(BRAVE_QUERIES), page_cursors=cursors,
              monthly_requests=used, last_requests=attempts)
    limited = bool(truncated or cursors or started < len(queries))
    outcome.update(state=('partial' if successes else 'error') if errors else 'ok',
                   requests_used=attempts, monthly_requests=used, raw_results=raw,
                   queries_attempted=started, queries_completed=completed, truncated_queries=truncated,
                   coverage_limited=limited, errors=errors[:5],
                   message=f'{len(jobs)} matches from {raw} results; {attempts} requests; '
                           f'{started}/{len(BRAVE_QUERIES)} query families checked; '
                           f'{truncated} page limits reached' + (f"; issues: {', '.join(errors[:3])}" if errors else ''))
    return _finish('brave', state, st, jobs, outcome, on_source)


def jooble_search(session: requests.Session, state: dict, sources: list[dict], *, per_run: int = 3,
                  on_source=None) -> tuple[list[dict], list[dict], dict]:
    from .collect import classify_region, clean_text, is_relevant, new_job, valid_url
    from .vacancy import assess_vacancy
    from .telemetry import source_started
    key = os.environ.get('JOOBLE_API_KEY', '').strip()
    if not key:
        return [], [], state
    if per_run <= 0:
        outcome={'name':'Jooble API','source_id':'api:jooble','sector':'Aggregator API','mode':'Aggregator API (regional key)',
                 'state':'skipped','jobs_found':0,'message':'Disabled by the configured per-run query budget'}
        if on_source:on_source(outcome,[])
        return [],[outcome],state
    st = dict(state.get('jooble') or {})
    host = os.environ.get('JOOBLE_API_HOST', '').strip().lower()
    outcome = {'name': 'Jooble API', 'source_id': 'api:jooble', 'sector': 'Aggregator API',
               'mode': 'Aggregator API (regional key)', 'coverage': 'Provider country coverage; not all LinkedIn jobs'}
    jobs = {}
    # Never send the key in the URL to a user-controlled non-Jooble host or redirect.
    if not re.fullmatch(r'(?:[a-z]{2}\.)?jooble\.org', host):
        outcome.update(state='error', reason='configuration', requests_used=0,
                       message='Set JOOBLE_API_HOST to the regional jooble.org hostname supplied with your country-specific key')
        return _finish('jooble', state, st, jobs, outcome, on_source)
    clock = time.time()
    day = datetime.fromtimestamp(clock, timezone.utc).date().isoformat()
    if st.get('request_day') != day:
        st.update(request_day=day, daily_requests=0)
    used = _number(st.get('daily_requests'))
    daily_limit = _integer('JOOBLE_DAILY_REQUEST_LIMIT', 96, 0, 100000)
    remaining = min(_integer('JOOBLE_MAX_REQUESTS_PER_RUN', 4, 1, 100), max(0, daily_limit-used))
    page_limit = _integer('JOOBLE_PAGES_PER_QUERY', 3, 1, 20)
    page_size = 50
    if clock < float(st.get('next_check') or 0) or remaining <= 0:
        outcome.update(state='cached', requests_used=0, daily_requests=used, coverage_limited=True,
                       message='Provider cooldown or configured daily request budget reached')
        return _finish('jooble', state, st, jobs, outcome, on_source)
    source_started(on_source, outcome)
    start = _number(st.get('index')) % len(JOOBLE_KEYWORDS)
    words = [JOOBLE_KEYWORDS[(start+i) % len(JOOBLE_KEYWORDS)] for i in range(min(per_run, len(JOOBLE_KEYWORDS)))]
    cursors = dict(st.get('page_cursors') or {})
    attempts = successes = raw = started = truncated = 0
    errors = []
    stop = False
    for word in words:
        if attempts >= remaining or stop:
            break
        started += 1
        page = min(page_limit, max(1, _number(cursors.get(word), 1)))
        page_ids = set()
        observed_count = 0
        started_at_first_page = page == 1
        while page <= page_limit and attempts < remaining:
            attempts += 1
            used += 1
            try:
                response = session.post(f'https://{host}/api/{key}', timeout=25, allow_redirects=False,
                                        json={'keywords': word, 'location': 'Bangladesh', 'page': page, 'ResultOnPage': page_size},
                                        headers={'Content-Type': 'application/json'})
                response.raise_for_status()
                if 300 <= response.status_code < 400:
                    raise ValueError('Unexpected redirect; check country endpoint')
                payload = response.json()
                if not isinstance(payload, dict) or not isinstance(payload.get('jobs'), list):
                    raise ValueError('Invalid job payload')
                results = payload['jobs']
                successes += 1
                raw += len(results)
                ids = {str(x.get('id') or x.get('link')) for x in results if isinstance(x, dict)}
                new_ids = ids - page_ids
                page_ids |= ids
                for item in results:
                    if not isinstance(item, dict):
                        continue
                    title = clean_text(item.get('title'), 200)
                    desc = clean_text(item.get('snippet'), 3000)
                    link = item.get('link') or ''
                    if not valid_url(link) or not is_relevant(title, desc) or not assess_vacancy(title, desc, link, source_kind='publisher').vacancy:
                        continue
                    # A query location is not proof of the location of every returned listing.
                    region = classify_region(item.get('location') or '', desc)
                    if not region:
                        continue
                    origin = clean_text(item.get('source'), 80)
                    job = new_job(title=title, company=item.get('company') or 'Employer not identified', url=link,
                                  source='Jooble API', sources=sources, description=desc,
                                  salary=item.get('salary') or 'Not disclosed', employment_type=item.get('type') or 'Not specified',
                                  source_name=f'Jooble · {origin}' if origin else 'Jooble',
                                  verification_level='Aggregator API', description_status='Aggregator snippet; publication date not provided', **region)
                    job['source_updated_at'] = str(item.get('updated') or '')
                    jobs[_job_key(job)] = job
                total = _number(payload.get('totalCount'), -1)
                observed_count += len(results)
                # A provider may return fewer items than ResultOnPage. Only
                # observed rows from page one establish totalCount coverage.
                # A resumed cursor continues until empty/repeated pages or its
                # explicit budget; it does not invent a count for earlier pages.
                exhausted = started_at_first_page and total >= 0 and observed_count >= total
                if results and not new_ids and not exhausted:
                    truncated += 1
                if not results or not new_ids or exhausted:
                    cursors.pop(word, None)
                    break
                page += 1
                if page > page_limit:
                    truncated += 1
                    cursors.pop(word, None)
                else:
                    cursors[word] = page
            except (requests.RequestException, ValueError, TypeError) as exc:
                code, retry_at = _cooldown(exc, clock)
                errors.append(f'HTTP {code}' if code else type(exc).__name__)
                cursors[word] = page
                if code in (401, 403, 429):
                    st['next_check'] = retry_at
                    stop = True
                break
    st.update(index=(start+started) % len(JOOBLE_KEYWORDS), page_cursors=cursors, daily_requests=used)
    outcome.update(state=('partial' if successes else 'error') if errors else 'ok',
                   requests_used=attempts, daily_requests=used, daily_request_limit=daily_limit,
                   raw_results=raw, queries_attempted=started, query_pool_size=len(JOOBLE_KEYWORDS),
                   truncated_queries=truncated, coverage_limited=bool(truncated or cursors or started<len(words)), errors=errors[:5],
                   message=f'{len(jobs)} matches from {raw} listings; {attempts} requests; '
                           f'{used}/{daily_limit} daily budget used' + (f"; issues: {', '.join(errors[:3])}" if errors else ''))
    return _finish('jooble', state, st, jobs, outcome, on_source)


def configured_count() -> int:
    return int(bool(os.environ.get('BRAVE_API_KEY','').strip()) and _integer('BRAVE_QUERIES_PER_RUN',2,0)>0) + \
           int(bool(os.environ.get('JOOBLE_API_KEY','').strip()) and _integer('JOOBLE_QUERIES_PER_RUN',3,0)>0)
