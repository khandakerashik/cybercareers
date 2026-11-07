"""Read job-alert emails you subscribed to (LinkedIn, Bdjobs, Indeed, Glassdoor, …).

This is how LinkedIn and Bdjobs vacancies reach the dashboard *without*
scraping those sites: you create job alerts on the platforms (e.g. LinkedIn
"information security" in Bangladesh, daily), they email you, and the
collector reads those emails from your own mailbox over IMAP (read-only,
messages are not marked as read). Only the email content is parsed; the
platform pages are never fetched.

Configure with environment variables (or GitHub Actions secrets):
  ALERT_IMAP_USER       mailbox login, e.g. a dedicated Gmail address
  ALERT_IMAP_PASSWORD   an *app password* (Gmail: Google Account → Security → App passwords)
  ALERT_IMAP_HOST       default imap.gmail.com
  ALERT_IMAP_FOLDER     default INBOX (a Gmail label such as "JobAlerts" also works)
  ALERT_LOOKBACK_DAYS   default 21
"""
from __future__ import annotations

import email
import email.policy
import imaplib
import logging
import os
import re
from datetime import datetime, timedelta, timezone
from urllib.parse import parse_qs, unquote, urlparse

from bs4 import BeautifulSoup

LOG = logging.getLogger(__name__)
SENDERS = ('linkedin.com', 'bdjobs.com', 'indeed.com', 'glassdoor.com', 'joblagbe.online', 'skill.jobs',
           'chakri.com', 'shomvob.co', 'careerjet.com.bd', 'jobs.com.bd', 'wellfound.com', 'jooble.org')

# platform -> (url regex with an id group, canonical url template, source label)
PATTERNS = [
    ('LinkedIn', re.compile(r'linkedin\.com/(?:comm/)?jobs/view/(?:[^/?#"]*-)?(\d{6,})', re.I), 'https://www.linkedin.com/jobs/view/{}/'),
    ('Bdjobs', re.compile(r'bdjobs\.com/[^"\s]*?(?:jobdetails?\.asp\?(?:[^"\s]*?&)?id=|/details/|/jobdetails/)(\d{5,})', re.I), 'https://jobs.bdjobs.com/jobdetails.asp?id={}'),
    ('Indeed', re.compile(r'indeed\.com/[^"\s]*?[?&]jk=([0-9a-f]{12,20})', re.I), 'https://www.indeed.com/viewjob?jk={}'),
    ('Glassdoor', re.compile(r'glassdoor\.[a-z.]+/[^"\s]*?(?:jobListingId|jl)=(\d{6,})', re.I), 'https://www.glassdoor.com/job-listing/index.htm?jl={}'),
]
NOISE = re.compile(r'^(view job|apply|apply now|easy apply|see all jobs|see more jobs|view all|unsubscribe|'
                   r'manage alerts?|job alert|new jobs?|recommended|promoted|actively recruiting|\d+ (?:applicants?|connections?).*)$', re.I)


def configured() -> bool:
    return bool(os.environ.get('ALERT_IMAP_USER') and os.environ.get('ALERT_IMAP_PASSWORD'))


def _unwrap(url: str) -> str:
    """Follow tracking wrappers that carry the destination in a query parameter."""
    for _ in range(3):
        q = parse_qs(urlparse(url).query)
        inner = next((v[0] for k, v in q.items() if k.lower() in ('url', 'u', 'redirect', 'target', 'dest', 'destination')
                      and v and v[0].startswith('http')), '')
        if not inner:
            break
        url = unquote(inner)
    return url


def _block_text(anchor) -> list[str]:
    """Text lines from the smallest container around a job link."""
    node = anchor
    for _ in range(5):
        node = node.parent
        if node is None:
            break
        text = node.get_text('\n', strip=True)
        if 30 <= len(text) <= 600:
            lines = [re.sub(r'\s+', ' ', x).strip(' ·|•-') for x in re.split(r'\n|·|\||•', text)]
            return [x for x in lines if x and not NOISE.match(x)]
    return []


def parse_alert_email(html: str, *, sender: str = '', received: str = '') -> list[dict]:
    """Extract (title, company, location, url, platform) rows from one alert email."""
    soup = BeautifulSoup(html or '', 'lxml')
    rows: dict[str, dict] = {}
    for a in soup.select('a[href]'):
        href = _unwrap(a.get('href', ''))
        for platform, rx, canonical in PATTERNS:
            m = rx.search(href)
            if not m:
                continue
            url = canonical.format(m.group(1))
            label = re.sub(r'\s+', ' ', a.get_text(' ', strip=True))
            row = rows.setdefault(url, {'url': url, 'platform': platform, 'title': '', 'company': '', 'location': '',
                                        'received': received})
            if label and not NOISE.match(label) and len(label) <= 160 and not row['title']:
                row['title'] = label
                lines = _block_text(a)
                rest = [x for x in lines if x != label and x.lower() != label.lower()]
                if rest:
                    row['company'] = rest[0][:120]
                if len(rest) > 1:
                    row['location'] = rest[1][:160]
            break
    return [r for r in rows.values() if r['title']]


def _html_of(msg) -> str:
    part = msg.get_body(preferencelist=('html', 'plain'))
    if part is None:
        return ''
    content = part.get_content()
    if part.get_content_type() == 'text/plain':
        content = re.sub(r'(https?://\S+)', r'<a href="\1">\1</a>', content)
    return content


def fetch_alert_rows(max_messages: int = 250) -> list[dict]:
    host = os.environ.get('ALERT_IMAP_HOST', 'imap.gmail.com')
    folder = os.environ.get('ALERT_IMAP_FOLDER', 'INBOX')
    days = int(os.environ.get('ALERT_LOOKBACK_DAYS', '21') or 21)
    since = (datetime.now(timezone.utc) - timedelta(days=days)).strftime('%d-%b-%Y')
    rows: list[dict] = []
    with imaplib.IMAP4_SSL(host, timeout=30) as box:
        box.login(os.environ['ALERT_IMAP_USER'], os.environ['ALERT_IMAP_PASSWORD'])
        box.select(f'"{folder}"' if ' ' in folder else folder, readonly=True)
        ids: list[bytes] = []
        for sender in SENDERS:
            typ, data = box.search(None, 'SINCE', since, 'FROM', f'"{sender}"')
            if typ == 'OK' and data and data[0]:
                ids.extend(data[0].split())
        for msg_id in sorted(set(ids), key=int, reverse=True)[:max_messages]:
            typ, data = box.fetch(msg_id, '(BODY.PEEK[])')
            if typ != 'OK' or not data or not isinstance(data[0], tuple):
                continue
            msg = email.message_from_bytes(data[0][1], policy=email.policy.default)
            try:
                received = email.utils.parsedate_to_datetime(msg.get('Date')).date().isoformat()
            except (TypeError, ValueError):
                received = ''
            rows.extend(parse_alert_email(_html_of(msg), sender=str(msg.get('From', '')), received=received))
    return rows


def rows_to_jobs(rows: list[dict], sources: list[dict]) -> list[dict]:
    from .collect import bangladesh_relevance, classify_region, is_relevant, new_job
    jobs = []
    for r in rows:
        if not is_relevant(r['title']):
            continue
        loc = r.get('location') or ''
        if r['platform'] == 'Bdjobs' and not loc:
            loc = 'Bangladesh'
        if bangladesh_relevance(loc, ''):
            region = {'region': 'Bangladesh', 'location': loc}
        else:
            region = classify_region(loc, '', remote=bool(re.search(r'remote', loc, re.I)))
            if not region:
                continue
        jobs.append(new_job(title=r['title'], company=r.get('company') or 'Employer not identified', url=r['url'],
                            source=f"{r['platform']} alert email", sources=sources, posted=r.get('received', ''),
                            description=f"{r['title']} — {r.get('company','')} — {loc}. Received via your {r['platform']} job alert; "
                                        f"open the original listing for the full description.",
                            source_name=f"{r['platform']} (job alert)",
                            verification_level='Email alert (subscribed)', description_status='Alert summary',
                            **region))
    return jobs


def collect_email_alerts(sources: list[dict], on_source=None) -> tuple[list[dict], list[dict]]:
    if not configured():
        return [], []
    outcome = {'name': 'Job-alert mailbox', 'source_id': 'email:alerts', 'sector': 'Job alerts',
               'mode': 'IMAP (subscribed alerts)'}
    try:
        rows = fetch_alert_rows()
        jobs = rows_to_jobs(rows, sources)
        outcome.update(state='ok', jobs_found=len(jobs), message=f'{len(jobs)} security roles from {len(rows)} alert listings')
    except (imaplib.IMAP4.error, OSError, KeyError, ValueError) as exc:
        jobs = []
        outcome.update(state='error', jobs_found=0, message=f'IMAP failed ({type(exc).__name__})')
    if on_source:
        on_source(outcome, jobs)
    return jobs, [outcome]
