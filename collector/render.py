"""Optional headless rendering for JavaScript-only career pages.

Enabled with RENDER_JS=1 and `pip install playwright && playwright install chromium`.
Pages are rendered only after the normal allow-list and robots.txt checks pass,
with the collector's honest User-Agent. No stealth plugins, fingerprint
spoofing or challenge solving: a page that shows a bot challenge is reported
as blocked, exactly like a plain HTTP fetch.
"""
from __future__ import annotations

import atexit
import logging
import os
import re
import shutil
import threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Callable

LOG = logging.getLogger(__name__)
_LOCK = threading.Lock()
_STATE: dict = {}
_EXECUTOR = ThreadPoolExecutor(max_workers=1, thread_name_prefix='career-browser')


def enabled() -> bool:
    return os.environ.get('RENDER_JS', '').strip().lower() in ('1', 'true', 'yes', 'on')


def looks_js_rendered(html: str) -> bool:
    """Heuristic: an app shell with very little visible text."""
    if not html:
        return False
    text = re.sub(r'<script.*?</script>|<style.*?</style>|<[^>]+>', ' ', html, flags=re.S | re.I)
    visible = len(re.sub(r'\s+', ' ', text).strip())
    if re.search(r'"@type"\s*:\s*"JobPosting"|itemtype=["\'][^"\']*JobPosting',html,re.I):
        return False
    if re.search(r'\bno\s+(?:(?:new|open|currently?|available|suitable)\s+){0,3}(?:jobs?|positions?|vacancies|roles?|openings?)\b',text,re.I):
        return False
    shell = re.search(r'id=["\'](?:root|app|__next|__nuxt|q-app)["\']|ng-app|data-reactroot|<app-root', html, re.I)
    return bool((visible < 700 and shell) or (visible < 120 and html.lower().count('<script') >= 4))


def _browser():
    if 'browser' not in _STATE:
        from playwright.sync_api import sync_playwright
        pw = sync_playwright().start()
        try:
            executable=os.environ.get('CHROMIUM_EXECUTABLE_PATH','').strip()
            if executable and not (Path(executable).is_file() and os.access(executable,os.X_OK)):
                raise ValueError('CHROMIUM_EXECUTABLE_PATH must identify an executable file')
            if not executable and not Path(pw.chromium.executable_path).exists():
                executable=shutil.which('chromium') or shutil.which('chromium-browser') or ''
            browser = pw.chromium.launch(**({'executable_path':executable} if executable else {}))
        except Exception:
            pw.stop()
            raise
        _STATE.update(pw=pw,browser=browser)
    return _STATE['browser']


def _render_page(url: str, user_agent: str, timeout_ms: int, allow_navigation: Callable[[str], bool] | None) -> str | None:
    """Run every Playwright operation on the same dedicated worker thread."""
    try:
        context = _browser().new_context(user_agent=user_agent, java_script_enabled=True)
        try:
            if allow_navigation:
                def route_request(route):
                    request = route.request
                    if request.is_navigation_request() and not allow_navigation(request.url):
                        route.abort()
                    elif request.resource_type in ('image', 'media', 'font'):
                        route.abort()
                    else:
                        route.continue_()
                context.route('**/*', route_request)
            page = context.new_page()
            # Careers pages with analytics/long polling may never reach networkidle.
            page.goto(url, wait_until='domcontentloaded', timeout=timeout_ms)
            try:
                page.wait_for_load_state('networkidle', timeout=min(4000, timeout_ms))
            except Exception:
                pass
            html = page.content()
        finally:
            context.close()
    except Exception as exc:  # pragma: no cover - depends on local browser
        LOG.info('JS render failed for %s: %s', url, type(exc).__name__)
        return None
    if re.search(r'<title[^>]*>[^<]*(just a moment|access denied|captcha|verify you are human)', html[:5000], re.I):
        return None
    return html


def render_page(url: str, user_agent: str, timeout_ms: int = 20000,
                *, allow_navigation: Callable[[str], bool] | None = None) -> str | None:
    if not enabled():
        return None
    # A mutex is insufficient: Playwright objects must stay on their creator
    # thread. Collector workers submit work here instead of reusing a browser
    # owned by another thread.
    return _EXECUTOR.submit(_render_page, url, user_agent, timeout_ms, allow_navigation).result()


def _close_browser() -> None:
    try:
        if 'browser' in _STATE:
            _STATE.pop('browser').close()
        if 'pw' in _STATE:
            _STATE.pop('pw').stop()
    except Exception:  # pragma: no cover
        pass


def close() -> None:
    with _LOCK:
        if _STATE:
            try:
                _EXECUTOR.submit(_close_browser).result()
            except RuntimeError:  # executor has already shut down at interpreter exit
                pass


atexit.register(close)
