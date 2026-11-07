"""Run the CyberCareers BD dashboard locally with ``python -m server.app``.

The frontend is served without extra web-server dependencies. Collection uses
``collector.collect``, requires the packages in requirements.txt, and is
available only through a deliberately restricted local refresh endpoint.
"""
from __future__ import annotations

import argparse
import json
import logging
import mimetypes
import os
import re
import threading
from datetime import datetime, timezone
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import unquote, urlsplit

ROOT = Path(__file__).resolve().parents[1]
PUBLIC_ROOT_FILES = frozenset({'index.html', 'styles.css', 'app.js', 'auth.js', 'config.js', '.nojekyll'})
PUBLIC_DATA_FILES = frozenset({'jobs.json', 'sources.json', 'status.json', 'source_health.json', 'progress.json', 'search_queries.json'})
PUBLIC_ASSET_FILES = frozenset({'favicon.svg'})
CONFIG_PATTERN = re.compile(r'^[A-Z][A-Z0-9_]*$')
LOG = logging.getLogger('cybercareers.local')


def load_local_env(path: Path | None = None) -> None:
    """Load simple KEY=value entries in a local .env without replacing real env vars.

    This is purposefully a minimal, non-executing dotenv reader. Only keys
    needed by our collector are passed via the current process environment.
    """
    path = path or ROOT / '.env'
    if not path.is_file():
        return
    allowed = {
        'MAX_FEED_SEARCHES', 'MAX_CAREER_PAGES', 'MAX_DETAIL_PAGES',
        'MAX_JOB_AGE_DAYS', 'REFRESH_INTERVAL_HOURS', 'COLLECT_WORKERS', 'RENDER_JS',
        'ALERT_IMAP_HOST', 'ALERT_IMAP_USER', 'ALERT_IMAP_PASSWORD', 'ALERT_IMAP_FOLDER', 'ALERT_LOOKBACK_DAYS',
        'BRAVE_API_KEY', 'BRAVE_QUERIES_PER_RUN', 'JOOBLE_API_KEY', 'JOOBLE_QUERIES_PER_RUN', 'CC_MASTER_KEY',
    }
    for line in path.read_text(encoding='utf-8-sig').splitlines():
        line = line.strip()
        if not line or line.startswith('#') or '=' not in line:
            continue
        key, value = line.split('=', 1)
        key = key.strip()
        if not CONFIG_PATTERN.fullmatch(key) or key not in allowed:
            continue
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "'\"":
            value = value[1:-1]
        os.environ.setdefault(key, value)


def public_path(path: str) -> Path | None:
    """Explicit allowlist prevents exposing .env, source code and repository files."""
    path = unquote(path)
    if '\x00' in path or '\\' in path or not path.startswith('/'):
        return None
    parts = path.split('/')
    if any(part in ('.', '..') for part in parts):
        return None
    if path == '/':
        path = '/index.html'
    name = path.lstrip('/')
    if name in PUBLIC_ROOT_FILES:
        return ROOT / name
    if name.startswith('data/') and name[5:] in PUBLIC_DATA_FILES:
        return ROOT / name
    if name.startswith('assets/') and name[7:] in PUBLIC_ASSET_FILES:
        return ROOT / name
    return None


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec='seconds')


class RefreshController:
    """One refresh at a time, in a worker thread; network is never required to boot."""

    def __init__(self, *, max_search_queries: int = 6, max_career_pages: int = 250, max_detail_pages: int = 450):
        self.max_search_queries = max(0, min(12, max_search_queries))
        self.max_career_pages = max(0, min(250, max_career_pages))
        self.max_detail_pages = max(0, min(600, max_detail_pages))
        self._lock = threading.Lock()
        self._running = False
        self._started_at: str | None = None
        self._finished_at: str | None = None
        self._last_error: str | None = None
        self._last_result: dict | None = None
        self._progress: dict = {'running':False,'checked':0,'total':0,'remaining':0, 'phase':'idle'}

    def status(self) -> dict:
        with self._lock:
            return {
                'running': self._running,
                'started_at': self._started_at,
                'finished_at': self._finished_at,
                'last_error': self._last_error,
                'last_result': self._last_result,
                'progress': dict(self._progress),
                'no_paid_api': True,
            }

    def start(self) -> bool:
        with self._lock:
            if self._running:
                return False
            self._running = True
            self._started_at = utc_now()
            self._last_error = None
            self._last_result = None
            self._progress = {'running': True,'checked':0,'total':0,'remaining':0,'phase':'starting','current_source':'Starting scan'}
        threading.Thread(target=self._worker, name='cybercareers-refresh', daemon=True).start()
        return True

    def _handle_progress(self, update: dict) -> None:
        with self._lock:
            self._progress = dict(update)

    def _worker(self) -> None:
        try:
            from collector.collect import run
            LOG.info('Job collection started (feed searches: %d, official pages: %d, detail budget: %d)',
                     self.max_search_queries, self.max_career_pages, self.max_detail_pages)
            report = run(max_queries=self.max_search_queries,
                         max_career_pages=self.max_career_pages,
                         max_detail_pages=self.max_detail_pages,
                         on_progress=self._handle_progress)
            # Do not expose internal request traces or arbitrary exception text to browsers.
            summary = {field: report.get(field) for field in (
                'updated_at', 'jobs_count', 'new_candidates', 'new_jobs_count', 'queries_run', 'bangladesh_jobs', 'international_jobs',
                'official_career_targets_checked', 'official_career_targets_reachable',
                'active_ats_boards', 'errors',
            )}
            with self._lock:
                self._last_result = summary
            LOG.info('Job collection complete: %s jobs, %s candidates',
                     report.get('jobs_count', 0), report.get('new_candidates', 0))
        except Exception:
            LOG.exception('Refresh failed; previous job data remains available')
            with self._lock:
                self._last_error = 'Job collection failed. See the local terminal for details.'
                self._progress.update({'running':False,'phase':'error','current_source':'Collection interrupted'})
        finally:
            with self._lock:
                self._finished_at = utc_now()
                self._running = False
                self._progress['running'] = False


def make_handler(controller: RefreshController, bind_host: str = '127.0.0.1'):
    """Return a handler class for local HTTP use and isolated tests."""
    safe_hosts = {'localhost', '127.0.0.1', '::1', bind_host.lower()}

    class LocalHandler(BaseHTTPRequestHandler):
        server_version = 'CyberCareersBD/1.1'
        sys_version = ''

        def _host_allowed(self) -> bool:
            raw = self.headers.get('Host', '')
            try:
                parsed = urlsplit('http://' + raw)
                return bool(parsed.hostname and parsed.hostname.lower() in safe_hosts)
            except ValueError:
                return False

        def _headers(self, code: int, mime_type: str, body_length: int) -> None:
            self.send_response(code)
            self.send_header('Content-Type', mime_type)
            self.send_header('Content-Length', str(body_length))
            self.send_header('Cache-Control', 'no-store')
            self.send_header('X-Content-Type-Options', 'nosniff')
            self.send_header('Referrer-Policy', 'strict-origin-when-cross-origin')
            self.send_header('X-Frame-Options', 'DENY')
            self.send_header('Cross-Origin-Resource-Policy', 'same-origin')
            self.end_headers()

        def _reply(self, code: int, value: dict, *, head: bool = False) -> None:
            body = json.dumps(value, ensure_ascii=False).encode('utf-8')
            self._headers(code, 'application/json; charset=utf-8', len(body))
            if not head:
                self.wfile.write(body)

        def _serve(self, *, head: bool = False) -> None:
            if not self._host_allowed():
                self._reply(HTTPStatus.FORBIDDEN, {'error': 'Unrecognized request host'}, head=head)
                return
            url = urlsplit(self.path)
            if url.path == '/api/health':
                try:
                    data = json.loads((ROOT / 'data/jobs.json').read_text(encoding='utf-8'))
                    count = len(data.get('jobs', []))
                except (ValueError, OSError):
                    count = 0
                self._reply(HTTPStatus.OK, {
                    'ok': True, 'mode': 'local', 'jobs_count': count,
                    'no_paid_api': True,
                }, head=head)
                return
            if url.path == '/api/refresh/status':
                self._reply(HTTPStatus.OK, controller.status(), head=head)
                return
            file = public_path(url.path)
            if file is None or not file.is_file():
                self._reply(HTTPStatus.NOT_FOUND, {'error': 'Not found'}, head=head)
                return
            mime = mimetypes.guess_type(str(file))[0] or 'application/octet-stream'
            if file.suffix == '.js':
                mime = 'text/javascript'
            if file.suffix in ('.html', '.js', '.css', '.svg', '.json'):
                mime += '; charset=utf-8'
            body = file.read_bytes()
            self._headers(HTTPStatus.OK, mime, len(body))
            if not head:
                self.wfile.write(body)

        def do_GET(self) -> None:
            self._serve()

        def do_HEAD(self) -> None:
            self._serve(head=True)

        def do_POST(self) -> None:
            if not self._host_allowed():
                self._reply(HTTPStatus.FORBIDDEN, {'error': 'Unrecognized request host'})
                return
            if urlsplit(self.path).path != '/api/refresh':
                self._reply(HTTPStatus.NOT_FOUND, {'error': 'Not found'})
                return
            # Prevent a website elsewhere from initiating fetches against a local
            # user's collector. No Access-Control-Allow-Origin is ever emitted.
            origin = self.headers.get('Origin')
            expected = 'http://' + self.headers.get('Host', '')
            if origin and origin != expected:
                self._reply(HTTPStatus.FORBIDDEN, {'error': 'Cross-origin refresh denied'})
                return
            if (self.headers.get('X-CyberCareers-Action') != 'refresh' or
                    self.headers.get('Content-Type', '').split(';')[0].strip().lower() != 'application/json'):
                self._reply(HTTPStatus.FORBIDDEN, {'error': 'Local refresh header required'})
                return
            try:
                length = int(self.headers.get('Content-Length', '0'))
            except ValueError:
                length = -1
            if length < 0 or length > 128:
                self._reply(HTTPStatus.BAD_REQUEST, {'error': 'Invalid request size'})
                return
            raw = self.rfile.read(length)
            try:
                arguments = json.loads(raw)
            except (UnicodeDecodeError, ValueError):
                self._reply(HTTPStatus.BAD_REQUEST, {'error': 'Expected a JSON object'})
                return
            if arguments != {}:
                self._reply(HTTPStatus.BAD_REQUEST, {'error': 'This action accepts no parameters'})
                return
            started = controller.start()
            self._reply(HTTPStatus.ACCEPTED if started else HTTPStatus.CONFLICT,
                        {'started': started, **controller.status()})

        def log_message(self, format: str, *args: object) -> None:
            LOG.info('%s %s', self.address_string(), format % args)

    return LocalHandler


def positive_integer_or_zero(value: str) -> int:
    n = int(value)
    if n < 0:
        raise argparse.ArgumentTypeError('Must be zero or a positive integer')
    return n


def main(argv: list[str] | None = None) -> int:
    load_local_env()
    parser = argparse.ArgumentParser(description='Run CyberCareers BD on your computer')
    parser.add_argument('--host', default='127.0.0.1',
                        help='Bind address; defaults to local access only (127.0.0.1)')
    parser.add_argument('--port', type=positive_integer_or_zero, default=8000,
                        help='HTTP port (default: 8000; 0 selects an available port)')
    parser.add_argument('--no-refresh-on-start', action='store_true',
                        help='Disable the default collection run on server startup')
    parser.add_argument('--refresh-every-hours', type=float,
                        default=float(os.getenv('REFRESH_INTERVAL_HOURS', '1')),
                        help='Collection interval in hours (default: 1; 0 disables scheduling)')
    parser.add_argument('--max-feed-searches', '--max-search-queries', type=positive_integer_or_zero,
                        default=int(os.getenv('MAX_FEED_SEARCHES', '6')),
                        help='Free remote-feed keyword searches per due run, max 12')
    parser.add_argument('--max-career-pages', type=positive_integer_or_zero,
                        default=int(os.getenv('MAX_CAREER_PAGES', '250')),
                        help='Official career sources per hourly refresh, max 250')
    parser.add_argument('--max-detail-pages', type=positive_integer_or_zero,
                        default=int(os.getenv('MAX_DETAIL_PAGES', '450')),
                        help='Official job detail URL budget per refresh, max 600')
    args = parser.parse_args(argv)
    if args.port > 65535:
        parser.error('--port must be 0 through 65535')
    if not 0 <= args.refresh_every_hours <= 8760:
        parser.error('--refresh-every-hours must be between 0 and 8760')
    logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(message)s')
    controller = RefreshController(max_search_queries=args.max_feed_searches,
                                   max_career_pages=args.max_career_pages,
                                   max_detail_pages=args.max_detail_pages)
    try:
        server = ThreadingHTTPServer((args.host, args.port), make_handler(controller, args.host))
    except OSError as exc:
        parser.exit(status=1, message=f'Could not start server: {exc}\n')
    effective_port = server.server_address[1]
    visible_host = '127.0.0.1' if args.host == '0.0.0.0' else args.host
    print(f'CyberCareers BD is running at http://{visible_host}:{effective_port}/', flush=True)
    print('Press Ctrl+C to stop. Your skill profile stays in your browser.', flush=True)
    print('No paid API or key needed.', flush=True)
    if args.refresh_every_hours > 0:
        print(f'Automatic collection interval: {args.refresh_every_hours:g} hour(s).', flush=True)
    else:
        print('Automatic scheduled collection is disabled.', flush=True)
    if args.host not in ('127.0.0.1', 'localhost', '::1'):
        LOG.warning('Listening on a non-loopback interface. Use a trusted network and firewall.')
    stop = threading.Event()
    if args.refresh_every_hours > 0:
        def scheduled_refresh() -> None:
            while not stop.wait(args.refresh_every_hours * 3600):
                controller.start()
        threading.Thread(target=scheduled_refresh, name='cybercareers-scheduler',
                         daemon=True).start()
    if not args.no_refresh_on_start:
        controller.start()
    try:
        server.serve_forever(poll_interval=0.25)
    except KeyboardInterrupt:
        print('\nCyberCareers BD stopped.', flush=True)
    finally:
        stop.set()
        server.server_close()
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
