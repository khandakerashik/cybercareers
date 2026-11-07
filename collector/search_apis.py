"""Optional keyed APIs that legitimately surface listings from restricted portals.

* Brave Search API (free tier, BRAVE_API_KEY): a licensed web-search index.
  Site-scoped queries such as ``site:linkedin.com/jobs/view "information security"
  Bangladesh`` return the search engine's own title/snippet for LinkedIn,
  Bdjobs and other postings. The portal pages themselves are never fetched.
* Jooble REST API (free key on request, JOOBLE_API_KEY): a job aggregator with
  Bangladesh coverage that licenses listings from many boards.

Both are skipped silently when no key is configured.
"""
from __future__ import annotations

import logging
import os
import time

import requests

LOG = logging.getLogger(__name__)

BRAVE_QUERIES = [
    'site:linkedin.com/jobs/view "information security" Bangladesh',
    'site:linkedin.com/jobs/view "cyber security" Dhaka',
    'site:linkedin.com/jobs/view ("SOC analyst" OR "security engineer") Bangladesh',
    'site:linkedin.com/jobs/view ("penetration tester" OR VAPT OR "application security") Bangladesh',
    'site:bdjobs.com "information security"',
    'site:bdjobs.com ("cyber security" OR "IT security" OR "network security")',
    'site:bdjobs.com ("IT audit" OR "IS audit" OR "ICT risk")',
    'site:bdjobs.com ("SOC" OR "penetration" OR "VAPT")',
    '"information security" job circular bank Bangladesh',
    'সাইবার নিরাপত্তা নিয়োগ বিজ্ঞপ্তি',
    'তথ্য নিরাপত্তা কর্মকর্তা নিয়োগ',
    '"cyber security" vacancy Dhaka apply',
]
JOOBLE_KEYWORDS = ['information security', 'cyber security', 'security engineer', 'SOC analyst',
                   'penetration testing', 'IT audit', 'network security', 'security analyst', 'GRC']


def brave_search(session: requests.Session, state: dict, sources: list[dict], *, per_run: int = 2,
                 on_source=None) -> tuple[list[dict], list[dict], dict]:
    from .collect import indexed_result_to_job
    key = os.environ.get('BRAVE_API_KEY', '').strip()
    if not key or per_run <= 0:
        return [], [], state
    st = dict(state.get('brave', {}))
    offset = int(st.get('index', 0)) % len(BRAVE_QUERIES)
    queries = [BRAVE_QUERIES[(offset + i) % len(BRAVE_QUERIES)] for i in range(min(per_run, len(BRAVE_QUERIES)))]
    jobs: list[dict] = []
    raw = 0
    outcome = {'name': 'Brave Search API', 'source_id': 'api:brave', 'sector': 'Search API', 'mode': 'Licensed search index'}
    try:
        for q in queries:
            r = session.get('https://api.search.brave.com/res/v1/web/search', timeout=20,
                            params={'q': q, 'count': 20, 'freshness': 'pm', 'safesearch': 'off'},
                            headers={'Accept': 'application/json', 'X-Subscription-Token': key})
            r.raise_for_status()
            results = ((r.json() or {}).get('web') or {}).get('results') or []
            raw += len(results)
            for item in results:
                job = indexed_result_to_job(item, sources)
                if job:
                    jobs.append(job)
            time.sleep(1.1)  # free tier: 1 request / second
        outcome.update(state='ok', jobs_found=len(jobs), message=f'{len(jobs)} matches from {raw} results ({len(queries)} queries)')
    except (requests.RequestException, ValueError) as exc:
        code = getattr(getattr(exc, 'response', None), 'status_code', None)
        outcome.update(state='error', jobs_found=len(jobs), message=f'HTTP {code}' if code else type(exc).__name__)
    st['index'] = (offset + len(queries)) % len(BRAVE_QUERIES)
    state = {**state, 'brave': st}
    if on_source:
        on_source(outcome, jobs)
    return jobs, [outcome], state


def jooble_search(session: requests.Session, state: dict, sources: list[dict], *, per_run: int = 3,
                  on_source=None) -> tuple[list[dict], list[dict], dict]:
    from .collect import classify_region, clean_text, is_relevant, new_job, valid_url
    key = os.environ.get('JOOBLE_API_KEY', '').strip()
    if not key or per_run <= 0:
        return [], [], state
    st = dict(state.get('jooble', {}))
    offset = int(st.get('index', 0)) % len(JOOBLE_KEYWORDS)
    words = [JOOBLE_KEYWORDS[(offset + i) % len(JOOBLE_KEYWORDS)] for i in range(min(per_run, len(JOOBLE_KEYWORDS)))]
    jobs: list[dict] = []
    raw = 0
    outcome = {'name': 'Jooble API', 'source_id': 'api:jooble', 'sector': 'Aggregator API', 'mode': 'Aggregator API (key)'}
    try:
        for word in words:
            r = session.post(f'https://jooble.org/api/{key}', timeout=25,
                             json={'keywords': word, 'location': 'Bangladesh', 'page': '1'},
                             headers={'Content-Type': 'application/json'})
            r.raise_for_status()
            for item in (r.json() or {}).get('jobs') or []:
                raw += 1
                title = clean_text(item.get('title'), 200)
                desc = clean_text(item.get('snippet'), 3000)
                link = item.get('link') or ''
                if not valid_url(link) or not is_relevant(title, desc):
                    continue
                region = classify_region(item.get('location') or 'Bangladesh', desc) or \
                    {'region': 'Bangladesh', 'location': item.get('location') or 'Bangladesh (verify location)'}
                origin = clean_text(item.get('source'), 80)
                jobs.append(new_job(title=title, company=item.get('company') or 'Employer not identified', url=link,
                                    source='Jooble API', sources=sources, description=desc,
                                    posted=item.get('updated', ''), salary=item.get('salary') or 'Not disclosed',
                                    employment_type=item.get('type') or 'Not specified',
                                    source_name=f'Jooble · {origin}' if origin else 'Jooble',
                                    verification_level='Aggregator API', description_status='Aggregator snippet', **region))
        outcome.update(state='ok', jobs_found=len(jobs), message=f'{len(jobs)} matches from {raw} listings')
    except (requests.RequestException, ValueError) as exc:
        code = getattr(getattr(exc, 'response', None), 'status_code', None)
        outcome.update(state='error', jobs_found=len(jobs), message=f'HTTP {code}' if code else type(exc).__name__)
    st['index'] = (offset + len(words)) % len(JOOBLE_KEYWORDS)
    state = {**state, 'jooble': st}
    if on_source:
        on_source(outcome, jobs)
    return jobs, [outcome], state


def configured_count() -> int:
    return int(bool(os.environ.get('BRAVE_API_KEY'))) + int(bool(os.environ.get('JOOBLE_API_KEY')))
