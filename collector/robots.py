"""RFC 9309 robots.txt matcher.

Python's ``urllib.robotparser`` uses *first* matching rule in file order and has
no ``*`` / ``$`` wildcard support. Sites that write::

    User-agent: *
    Disallow: /
    Allow: /careers/

are therefore wrongly treated as blocking ``/careers/`` (RFC 9309 says the
longest match wins, and ``Allow`` wins ties). This implementation follows the
RFC so that pages a site *does* permit are no longer skipped. It never makes
a disallowed path allowed.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from urllib.parse import unquote, urlparse


@dataclass
class _Group:
    agents: list[str] = field(default_factory=list)
    rules: list[tuple[bool, str]] = field(default_factory=list)  # (allow, pattern)
    crawl_delay: float | None = None


def _pattern_regex(pattern: str) -> re.Pattern:
    anchored = pattern.endswith('$')
    if anchored:
        pattern = pattern[:-1]
    body = '.*'.join(re.escape(part) for part in pattern.split('*'))
    return re.compile(body + ('$' if anchored else ''))


def _normalise(path: str) -> str:
    # Compare decoded paths, but keep %2F distinct from '/' semantics simple.
    try:
        return unquote(path)
    except Exception:  # pragma: no cover - defensive
        return path


class RobotsPolicy:
    def __init__(self, text: str = ''):
        self.groups: list[_Group] = []
        self._parse(text or '')

    def _parse(self, text: str) -> None:
        current: _Group | None = None
        last_was_agent = False
        for raw in text.splitlines():
            line = raw.split('#', 1)[0].strip()
            if ':' not in line:
                continue
            key, value = line.split(':', 1)
            key = key.strip().lower()
            value = value.strip()
            if key == 'user-agent':
                if current is None or not last_was_agent:
                    current = _Group()
                    self.groups.append(current)
                current.agents.append(value.lower())
                last_was_agent = True
                continue
            last_was_agent = False
            if current is None:
                continue
            if key in ('allow', 'disallow'):
                if value:
                    current.rules.append((key == 'allow', _normalise(value)))
            elif key == 'crawl-delay':
                try:
                    current.crawl_delay = float(value)
                except ValueError:
                    pass

    def _rules_for(self, user_agent: str) -> tuple[list[tuple[bool, str]], float | None]:
        token = re.split(r'[/\s(]', (user_agent or '').strip(), maxsplit=1)[0].lower()
        matched = [g for g in self.groups if token and any(a != '*' and token.startswith(a) for a in g.agents)]
        if not matched:
            matched = [g for g in self.groups if '*' in g.agents]
        rules: list[tuple[bool, str]] = []
        delay = None
        for g in matched:
            rules.extend(g.rules)
            if g.crawl_delay is not None:
                delay = g.crawl_delay if delay is None else max(delay, g.crawl_delay)
        return rules, delay

    def can_fetch(self, user_agent: str, url: str) -> bool:
        parts = urlparse(url)
        target = _normalise((parts.path or '/') + (('?' + parts.query) if parts.query else ''))
        if target == '/robots.txt':
            return True
        rules, _ = self._rules_for(user_agent)
        best_len, best_allow = -1, True
        for allow, pattern in rules:
            if _pattern_regex(pattern).match(target):
                length = len(pattern)
                if length > best_len or (length == best_len and allow):
                    best_len, best_allow = length, allow
        return best_allow

    def crawl_delay(self, user_agent: str) -> float | None:
        return self._rules_for(user_agent)[1]


ALLOW_ALL = RobotsPolicy('')
