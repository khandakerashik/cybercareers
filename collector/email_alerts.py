"""Read subscribed job alerts without requesting pages from restricted portals.

HTML and plain-text emails are parsed per posting, including country-subdomain
LinkedIn links and query-encoded tracking links. IMAP is read-only. A UID cursor
in feed_state drains any backlog across hourly runs without rereading the same
newest messages forever. Email receipt time is never a job publication date.
"""
from __future__ import annotations

import copy
import email
import email.policy
import html as html_lib
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
NOISE = re.compile(r'^(?:view(?: this)? job|apply|apply now|easy apply|see all jobs|see more jobs|view all|unsubscribe|'
                   r'manage alerts?|job alert|new jobs?|recommended|promoted|actively recruiting|'
                   r'job details|view (?:job details|role|opening)|learn more|'
                   r'\d+ (?:applicants?|connections?).*|\d+\s*(?:hours?|days?|weeks?)\s+ago|'
                   r'save(?: job)?|be an early applicant|see who you know|hiring now)$', re.I)
LOCATION = re.compile(r'\b(?:bangladesh|dhaka|chattogram|chittagong|sylhet|rajshahi|khulna|rangpur|'
                      r'gazipur|narayanganj|barishal|mymensingh|cumilla|remote|hybrid|on.site|'
                      r'worldwide|global|anywhere|apac|asia|united states|usa|canada|australia|'
                      r'india|singapore|london|united kingdom|germany|pakistan|new york)\b|বাংলাদেশ|ঢাকা', re.I)
ROLE = re.compile(r'\b(?:engineer|analyst|officer|manager|consultant|specialist|architect|auditor|lead|'
                  r'head|director|ciso|intern|trainee|administrator|researcher|tester|executive)\b|কর্মকর্তা|প্রকৌশলী', re.I)


def configured() -> bool:
    return bool(os.environ.get('ALERT_IMAP_USER') and os.environ.get('ALERT_IMAP_PASSWORD'))


def _bounded_env(name: str, default: int, low: int, high: int) -> int:
    try:
        return min(high, max(low, int(os.environ.get(name, str(default)).strip())))
    except (TypeError, ValueError):
        return default


def _unwrap(url: str) -> str:
    """Decode destination-bearing tracking links locally; never fetch them."""
    url = html_lib.unescape(str(url or '').strip())
    for _ in range(5):
        try:
            q = parse_qs(urlparse(url).query)
        except ValueError:
            return ''
        inner = ''
        for key, values in q.items():
            if key.casefold() not in ('url', 'u', 'redirect', 'redirecturl', 'target', 'dest', 'destination') or not values:
                continue
            candidate = values[0]
            for _ in range(2):
                if candidate.startswith(('http://', 'https://')):
                    break
                candidate = unquote(candidate)
            if candidate.startswith(('http://', 'https://')):
                inner = candidate
                break
        if not inner or inner == url:
            break
        url = html_lib.unescape(inner)
    return url


def canonical_portal_job(url: str) -> tuple[str, str] | None:
    """Return an exact posting identity; reject search pages and look-alike hosts.

    This helper is shared by index ingestion and deduplication. A domain in a
    query string or an attacker hostname containing 'linkedin.com' is not proof
    that a URL belongs to LinkedIn.
    """
    try:
        u = urlparse(_unwrap(url))
        host = (u.hostname or '').casefold().rstrip('.')
        if u.scheme not in ('http', 'https') or u.username or u.password or u.port not in (None, 80, 443):
            return None
    except (ValueError, TypeError):
        return None
    query = {k.casefold(): v for k, v in parse_qs(u.query).items()}
    def belongs(domain):
        return host == domain or host.endswith('.' + domain)
    if belongs('linkedin.com'):
        m = re.fullmatch(r'/(?:comm/)?jobs/view/(?:[^/]*-)?(\d+)/?', u.path, re.I)
        ident = m.group(1) if m else ''
        if not ident and re.match(r'^/(?:comm/)?jobs(?:/|$)', u.path):
            ident = (query.get('currentjobid') or [''])[0]
        if re.fullmatch(r'\d+', ident or ''):
            return 'LinkedIn', f'https://www.linkedin.com/jobs/view/{ident}/'
    elif belongs('bdjobs.com'):
        m = re.search(r'/(?:details|jobdetails)/(\d+)(?:/|$)', u.path, re.I)
        ident = m.group(1) if m else ''
        if re.search(r'/jobdetails?\.(?:asp|aspx|php)$', u.path, re.I):
            ident = (query.get('id') or query.get('jobid') or [''])[0]
        if re.fullmatch(r'\d+', ident or ''):
            return 'Bdjobs', f'https://jobs.bdjobs.com/jobdetails.asp?id={ident}'
    elif belongs('indeed.com') or re.fullmatch(r'(?:[a-z0-9-]+\.)?indeed\.(?:co\.uk|ca|com\.au|co\.in)', host):
        ident = (query.get('jk') or query.get('vjk') or [''])[0]
        if re.fullmatch(r'[0-9a-f]{12,20}', ident, re.I):
            return 'Indeed', f'https://www.indeed.com/viewjob?jk={ident.lower()}'
    elif belongs('glassdoor.com') or re.fullmatch(r'(?:[a-z0-9-]+\.)?glassdoor\.(?:co\.uk|ca|com\.au|co\.in)', host):
        ident = (query.get('joblistingid') or query.get('jl') or [''])[0]
        if re.fullmatch(r'\d+', ident):
            return 'Glassdoor', f'https://www.glassdoor.com/job-listing/index.htm?jl={ident}'
    return None


def _lines(node) -> list[str]:
    lines = [re.sub(r'\s+', ' ', x).strip(' ·|•\t') for x in node.get_text('\n', strip=True).splitlines()]
    return list(dict.fromkeys(x for x in lines if x and not NOISE.fullmatch(x) and not x.startswith(('https://', 'http://'))))


def _block_text(anchor) -> list[str]:
    """Choose a full single-job card; never mix metadata from neighbouring jobs."""
    identity = canonical_portal_job(anchor.get('href', ''))
    best: list[str] = []
    node = anchor
    for _ in range(12):
        node = node.parent
        if node is None or node.name in ('html', 'body', '[document]'):
            break
        ids = {canonical_portal_job(a.get('href', '')) for a in node.select('a[href]')}
        ids.discard(None)
        if any(i != identity for i in ids):
            break
        if len(node.get_text(' ', strip=True)) > 2400:
            break
        lines = _lines(node)
        if lines:
            best = lines
        # Do not stop at a title-only nested <td>; metadata may be in sibling cells.
    return best


def _metadata(lines: list[str], title: str) -> tuple[str, str, str]:
    rest = [line for line in lines if line.casefold() != title.casefold()
            and line.casefold() not in title.casefold() and not NOISE.fullmatch(line)]
    # Some alerts use Company · Dhaka, Bangladesh on one line.
    parts = [p.strip() for line in rest for p in re.split(r'\s*[·|•]\s*', line) if p.strip()]
    locations = [x for x in parts if LOCATION.search(x) and len(x) < 200
                 and not re.search(r'\b(?:bank|ltd|limited|plc|inc|corporation|technologies|university)\b', x, re.I)]
    company = next((x for x in parts if x not in locations and len(x) <= 150
                    and not re.match(r'^(?:your|jobs? (?:for|in)|salary|posted|\d+ new|view |this job)', x, re.I)), '')
    return company, ' · '.join(locations[:2]), ' '.join(lines)[:2400]


def parse_alert_email(html: str, *, sender: str = '', received: str = '') -> list[dict]:
    """Extract posting rows from HTML; attribution stays inside each job card."""
    soup = BeautifulSoup(html or '', 'lxml')
    for node in soup.select('script, style'):
        node.decompose()
    rows: dict[str, dict] = {}
    for anchor in soup.select('a[href]'):
        identity = canonical_portal_job(anchor.get('href', ''))
        if not identity:
            continue
        platform, url = identity
        label = re.sub(r'\s+', ' ', anchor.get_text(' ', strip=True)).strip()
        if not label:
            img = anchor.find('img', alt=True)
            label = str(anchor.get('aria-label') or (img.get('alt') if img else '') or '').strip()
        lines = _block_text(anchor)
        if not label or NOISE.fullmatch(label) or label.startswith(('http://', 'https://')):
            label = next((x for x in lines if ROLE.search(x) and not NOISE.fullmatch(x) and len(x) <= 200), '')
        if not label or len(label) > 200:
            continue
        company, location, description = _metadata(lines, label)
        row = {'url': url, 'platform': platform, 'title': label, 'company': company,
               'location': location, 'received': received, 'description': description}
        old = rows.get(url)
        if not old or sum(bool(row[k]) for k in ('company', 'location')) > sum(bool(old[k]) for k in ('company', 'location')):
            rows[url] = row
    return list(rows.values())


def _html_of(msg) -> str:
    part = msg.get_body(preferencelist=('html', 'plain'))
    if part is None:
        return ''
    content = part.get_content()
    if part.get_content_type() == 'text/html':
        return content
    # Preserve paragraph/card boundaries. URL labels are replaced by a nearby role.
    blocks = re.split(r'\n\s*\n', content.replace('\r\n', '\n'))
    html_blocks = []
    for block in blocks:
        pieces = []
        offset = 0
        for match in re.finditer(r'https?://[^\s<>]+', block):
            pieces.append(html_lib.escape(block[offset:match.start()]))
            url = match.group(0).rstrip(').,;]')
            escaped = html_lib.escape(url, quote=True)
            pieces.append('<a href="' + escaped + '">' + escaped + '</a>')
            offset = match.start() + len(url)
        pieces.append(html_lib.escape(block[offset:]))
        html_blocks.append('<div>' + ''.join(pieces).replace('\n', '<br>') + '</div>')
    return ''.join(html_blocks)


def fetch_alert_rows(max_messages: int | None = None, *, state: dict | None = None,
                     diagnostics: dict | None = None) -> list[dict]:
    host = os.environ.get('ALERT_IMAP_HOST') or 'imap.gmail.com'
    folder = os.environ.get('ALERT_IMAP_FOLDER') or 'INBOX'
    days = _bounded_env('ALERT_LOOKBACK_DAYS', 21, 1, 90)
    budget = max_messages if max_messages is not None else _bounded_env('ALERT_MAX_MESSAGES', 500, 1, 5000)
    since = (datetime.now(timezone.utc) - timedelta(days=days)).strftime('%d-%b-%Y')
    rows: list[dict] = []
    diagnostics = diagnostics if diagnostics is not None else {}
    diagnostics.update(messages_read=0, messages_failed=0, remaining_messages=0)
    with imaplib.IMAP4_SSL(host, timeout=30) as box:
        box.login(os.environ['ALERT_IMAP_USER'], os.environ['ALERT_IMAP_PASSWORD'])
        typ, _ = box.select('"' + folder.replace('"', '') + '"', readonly=True)
        if typ != 'OK':
            raise imaplib.IMAP4.error('Cannot select alert folder')
        _, validity_data = box.response('UIDVALIDITY')
        validity = str((validity_data or [None])[0] or '')
        scope = '|'.join((host, os.environ['ALERT_IMAP_USER'], folder, validity))
        previous = (state or {}).get('alert_mailbox') or {}
        seen = set(previous.get('processed_uids') or []) if validity and previous.get('scope') == scope else set()
        ids: set[bytes] = set()
        for sender in SENDERS:
            typ, data = box.uid('search', None, 'SINCE', since, 'FROM', f'"{sender}"')
            if typ != 'OK':
                raise imaplib.IMAP4.error('Alert search failed')
            if data and data[0]:
                ids.update(data[0].split())
        valid_ids = {x for x in ids if x.isdigit()}
        seen &= {x.decode('ascii') for x in valid_ids}
        pending = sorted((x for x in valid_ids if x.decode('ascii') not in seen), key=int)
        # Prioritise fresh leads while reserving a quarter of each run for backlog.
        # When the budget is one, alternate newest/oldest across successful runs.
        count = max(0, int(budget))
        turn = int(previous.get('selection_turn') or 0) if previous.get('scope') == scope else 0
        if len(pending) <= count:
            chosen = list(reversed(pending))
        elif count == 1:
            chosen = [pending[-1] if turn % 2 == 0 else pending[0]]
        elif count > 1:
            oldest_count = max(1, count // 4)
            fresh_count = count - oldest_count
            chosen = list(reversed(pending[-fresh_count:])) + pending[:oldest_count]
        else:
            chosen = []
        diagnostics.update(matched_messages=len(valid_ids), remaining_messages=max(0, len(pending) - len(chosen)))
        for uid in chosen:
            typ, data = box.uid('fetch', uid, '(BODY.PEEK[])')
            payload = next((x[1] for x in (data or []) if isinstance(x, tuple) and isinstance(x[1], bytes)), None)
            if typ != 'OK' or payload is None:
                diagnostics['messages_failed'] += 1
                continue
            try:
                msg = email.message_from_bytes(payload, policy=email.policy.default)
                sender = email.utils.parseaddr(str(msg.get('From', '')))[1].rsplit('@', 1)[-1].casefold()
                if not any(sender == domain or sender.endswith('.' + domain) for domain in SENDERS):
                    seen.add(uid.decode('ascii'))
                    continue
                try:
                    received = email.utils.parsedate_to_datetime(msg.get('Date')).date().isoformat()
                except (TypeError, ValueError, OverflowError):
                    received = ''
                rows.extend(parse_alert_email(_html_of(msg), sender=sender, received=received))
            except (ValueError, TypeError, UnicodeError):
                diagnostics['messages_failed'] += 1
                continue
            seen.add(uid.decode('ascii'))
            diagnostics['messages_read'] += 1
        if state is not None and validity:
            state['alert_mailbox'] = {'scope': scope, 'processed_uids': sorted(seen, key=int),
                                      'selection_turn': turn + int(bool(chosen))}
    return rows


def rows_to_jobs(rows: list[dict], sources: list[dict], *, diagnostics: dict | None = None) -> list[dict]:
    from .collect import bangladesh_relevance, classify_region, is_relevant, new_job
    from .vacancy import assess_vacancy
    jobs = {}
    diagnostics = diagnostics if diagnostics is not None else {}
    diagnostics.update(rejected_irrelevant=0, unresolved_location=0)
    for row in rows:
        title, desc = row.get('title', ''), row.get('description', '')
        if not is_relevant(title, desc) or not assess_vacancy(title, desc, row.get('url', ''), source_kind='alert').vacancy:
            diagnostics['rejected_irrelevant'] += 1
            continue
        loc = row.get('location') or ''
        if row['platform'] == 'Bdjobs' and not loc:
            loc = 'Bangladesh'
        if bangladesh_relevance(loc, ''):
            region = {'region': 'Bangladesh', 'location': loc}
        else:
            region = classify_region(loc, '', remote=bool(re.search(r'remote', loc, re.I)))
            if not region:
                diagnostics['unresolved_location'] += 1
                continue
        job = new_job(title=title, company=row.get('company') or 'Employer not identified', url=row['url'],
                      source=f"{row['platform']} alert email", sources=sources,
                      description=desc or f"{title} — {row.get('company', '')} — {loc}. Open the original listing for details.",
                      source_name=f"{row['platform']} (job alert)", verification_level='Email alert (subscribed)',
                      description_status='Alert summary; publication date not provided', **region)
        job['posted_at'] = ''
        job['alert_received_at'] = row.get('received') or ''
        if row.get('received'):
            job['last_seen_at'] = row['received']
            # Re-reading an old email is not a new observation of the posting.
            job['last_observed_at'] = row['received']
        previous = jobs.get(row['url'])
        if not previous or (job['alert_received_at'], len(job['description'])) > (previous.get('alert_received_at', ''), len(previous.get('description', ''))):
            jobs[row['url']] = job
    return list(jobs.values())


def collect_email_alerts(sources: list[dict], on_source=None, *, state: dict | None = None) -> tuple[list[dict], list[dict]]:
    if not configured():
        return [], []
    outcome = {'name': 'Job-alert mailbox', 'source_id': 'email:alerts', 'sector': 'Job alerts',
               'mode': 'IMAP (subscribed alerts)', 'coverage': 'Subscribed alerts only; not all LinkedIn jobs',
               'upstream_frequency': 'LinkedIn alerts are daily or weekly'}
    stats: dict = {}
    try:
        # Parsing/conversion must succeed before acknowledging UIDs. The outer
        # collector persists this checkpoint with its successfully merged jobs.
        staged_state = copy.deepcopy(state) if state is not None else None
        rows = fetch_alert_rows(state=staged_state, diagnostics=stats)
        jobs = rows_to_jobs(rows, sources, diagnostics=stats)
        if state is not None and staged_state is not None and 'alert_mailbox' in staged_state:
            state['alert_mailbox'] = staged_state['alert_mailbox']
        partial = bool(stats.get('remaining_messages') or stats.get('messages_failed'))
        outcome.update(state='partial' if partial else 'ok', jobs_found=len(jobs), **stats,
                       message=f"{len(jobs)} security roles; {stats['messages_read']} new emails read; "
                               f"{stats.get('remaining_messages', 0)} awaiting next run; "
                               f"{stats.get('unresolved_location', 0)} listings without eligible location evidence")
    except (imaplib.IMAP4.error, OSError, KeyError, ValueError) as exc:
        jobs = []
        outcome.update(state='error', jobs_found=0, message=f'IMAP failed ({type(exc).__name__})')
    if on_source:
        on_source(outcome, jobs)
    return jobs, [outcome]
