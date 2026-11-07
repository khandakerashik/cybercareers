"""Your own RSS/Atom feeds, e.g. Google Alerts, Telegram-to-RSS bridges, company feeds.

Add entries to data/custom_feeds.json:

  [{"name": "Google Alert: information security job Bangladesh",
    "url": "https://www.google.com/alerts/feeds/XXXXXXXX/YYYYYYYY",
    "region": "auto", "enabled": true}]

Google Alerts → create alert → "Deliver to: RSS feed" gives such a URL. Items
are kept only when they look like a vacancy *and* pass the cybersecurity
relevance engine. Region "auto" routes Bangladesh evidence to the Bangladesh
dashboard and explicit worldwide/APAC remote roles to International.
"""
from __future__ import annotations

import re
import time
import xml.etree.ElementTree as ET
from urllib.parse import parse_qs, urlparse

import requests

JOB_SIGNAL = re.compile(r'\b(hiring|vacanc\w*|job|jobs|career|careers|circular|recruit\w*|position|opening|apply|'
                        r'we are looking)\b|নিয়োগ|নিয়োগ|চাকরি|বিজ্ঞপ্তি|শূন্যপদ|সার্কুলার', re.I)


def _unwrap_google(link: str) -> str:
    u = urlparse(link)
    if u.hostname and u.hostname.endswith('google.com') and u.path == '/url':
        q = parse_qs(u.query)
        return (q.get('url') or q.get('q') or [link])[0]
    return link


def parse_feed(xml_text: str | bytes, feed: dict, sources: list[dict]) -> list[dict]:
    from .collect import bangladesh_relevance, classify_region, clean_text, is_relevant, new_job, valid_url
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError:
        return []
    jobs = []
    for node in root.iter():
        if node.tag.split('}')[-1].lower() not in ('item', 'entry'):
            continue
        fields: dict[str, str] = {}
        link = ''
        for child in node:
            tag = child.tag.split('}')[-1].lower()
            if tag == 'link':
                link = link or child.get('href') or (child.text or '')
            else:
                fields.setdefault(tag, ''.join(child.itertext()))
        title = clean_text(fields.get('title'), 220)
        desc = clean_text(fields.get('description') or fields.get('summary') or fields.get('content'), 6000)
        link = _unwrap_google((link or fields.get('guid') or '').strip())
        if not valid_url(link) or not JOB_SIGNAL.search(title + ' ' + desc[:400]):
            continue
        # Strip " - Site name" suffixes and "Company: Role" prefixes common in feeds.
        role = re.sub(r'\s+[|–-]\s+[^|–-]{2,40}$', '', title)
        company = ''
        m = re.match(r'(.{2,80}?):\s+(.{4,160})$', role)
        if m and is_relevant(m.group(2)):
            company, role = m.group(1), m.group(2)
        if not is_relevant(role, desc):
            continue
        wanted = (feed.get('region') or 'auto').lower()
        region_field = fields.get('region') or fields.get('location') or ''
        if wanted == 'bangladesh' or (wanted == 'auto' and bangladesh_relevance(region_field or title, desc)):
            region = {'region': 'Bangladesh', 'location': region_field or 'Bangladesh (verify location)'}
        else:
            region = classify_region(region_field or title, desc, remote=True)
            if not region or (wanted == 'bangladesh'):
                continue
        jobs.append(new_job(title=role, company=company or 'Employer not identified', url=link, source='Custom feed',
                            sources=sources, description=desc, posted=fields.get('pubdate') or fields.get('published') or fields.get('updated') or '',
                            source_name=feed.get('name') or 'Custom feed', verification_level='User feed (unverified)',
                            description_status='Feed excerpt', **region))
    return jobs


def collect_custom_feeds(session: requests.Session, feeds: list[dict], state: dict, sources: list[dict], *,
                         clock: float | None = None, on_source=None) -> tuple[list[dict], list[dict], dict]:
    from .collect import valid_url
    clock = time.time() if clock is None else clock
    state = dict(state or {})
    jobs: list[dict] = []
    health: list[dict] = []
    for feed in feeds if isinstance(feeds, list) else []:
        if not isinstance(feed, dict) or not feed.get('enabled', True) or not valid_url(feed.get('url', '')):
            continue
        key = 'custom:' + feed['url']
        prev = state.get(key, {})
        if clock < float(prev.get('next_check', 0)):
            continue
        outcome = {'name': feed.get('name') or urlparse(feed['url']).hostname, 'source_id': key[:200],
                   'sector': 'Custom feed', 'mode': 'User RSS/Atom feed'}
        try:
            r = session.get(feed['url'], timeout=20, headers={'Accept': 'application/rss+xml, application/atom+xml, application/xml;q=0.9'})
            r.raise_for_status()
            found = parse_feed(r.content, feed, sources)
            jobs.extend(found)
            outcome.update(state='ok', jobs_found=len(found), message=f'{len(found)} security vacancies')
        except (requests.RequestException, ValueError) as exc:
            found = []
            code = getattr(getattr(exc, 'response', None), 'status_code', None)
            outcome.update(state='error', jobs_found=0, message=f'HTTP {code}' if code else type(exc).__name__)
        state[key] = {'next_check': clock + 60 * max(30, int(feed.get('poll_minutes', 60) or 60)), 'checked_at': clock}
        health.append(outcome)
        if on_source:
            on_source(outcome, found)
    return jobs, health, state
