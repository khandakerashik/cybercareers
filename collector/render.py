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
import threading

LOG = logging.getLogger(__name__)
_LOCK = threading.Lock()
_STATE: dict = {}


def enabled() -> bool:
    return os.environ.get('RENDER_JS', '').strip().lower() in ('1', 'true', 'yes', 'on')


def looks_js_rendered(html: str) -> bool:
    """Heuristic: an app shell with very little visible text."""
    if not html:
        return False
    text = re.sub(r'<script.*?</script>|<style.*?</style>|<[^>]+>', ' ', html, flags=re.S | re.I)
    visible = len(re.sub(r'\s+', ' ', text).strip())
    shell = re.search(r'id=["\'](?:root|app|__next|__nuxt|q-app)["\']|ng-app|data-reactroot|<app-root', html, re.I)
    return visible < 700 and bool(shell or html.count('<script') >= 4)


def _browser():
    if 'browser' not in _STATE:
        from playwright.sync_api import sync_playwright
        pw = sync_playwright().start()
        _STATE['pw'] = pw
        _STATE['browser'] = pw.chromium.launch()
        atexit.register(close)
    return _STATE['browser']


def render_page(url: str, user_agent: str, timeout_ms: int = 20000) -> str | None:
    if not enabled():
        return None
    with _LOCK:  # Playwright's sync API is single-threaded.
        try:
            context = _browser().new_context(user_agent=user_agent, java_script_enabled=True)
            try:
                page = context.new_page()
                page.goto(url, wait_until='networkidle', timeout=timeout_ms)
                html = page.content()
            finally:
                context.close()
        except Exception as exc:  # pragma: no cover - depends on local browser
            LOG.info('JS render failed for %s: %s', url, type(exc).__name__)
            return None
    if re.search(r'<title[^>]*>[^<]*(just a moment|access denied|captcha|verify you are human)', html[:5000], re.I):
        return None
    return html


def close() -> None:
    try:
        if 'browser' in _STATE:
            _STATE.pop('browser').close()
        if 'pw' in _STATE:
            _STATE.pop('pw').stop()
    except Exception:  # pragma: no cover
        pass
