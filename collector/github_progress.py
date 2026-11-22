"""Optional encrypted live collection progress through GitHub Checks.

The collection workflow's GITHUB_TOKEN creates one custom check for its run.
Only public run identifiers, a generic summary, and CCLIVE1 ciphertext are sent.
Current vault users unwrap the fresh run key with their existing KEK; there is
no master-key/CI recipient in the live envelope. No token is written to disk.

Run with ``python -m collector.github_progress``. Without complete GitHub
Actions configuration this behaves like the ordinary collector CLI. Publishing
is best effort and cannot turn a successful collection into a failed one.
"""
from __future__ import annotations

import argparse
import base64
import copy
import gzip
import json
import logging
import os
import re
import secrets
import threading
import time
from datetime import datetime, timezone
from typing import Mapping
from urllib.parse import urlencode

import requests
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

import vault

LOG = logging.getLogger(__name__)
FORMAT = 'CCLIVE1'
CHECK_NAME = 'CyberCareers live collection'
API_ROOT = 'https://api.github.com'
API_VERSION = '2026-03-10'
OUTPUT_LIMIT = 65_000  # Checks output.text has a 65,535-character limit.
RAW_LIMIT = 1024 * 1024
USER_LIMIT = 100
INTERVAL_SECONDS = 15.0
REQUEST_TIMEOUT = (2.0, 5.0)
FINISH_TIMEOUT = 15.0
REPOSITORY_RX = re.compile(r'[A-Za-z0-9][A-Za-z0-9_.-]{0,99}/[A-Za-z0-9][A-Za-z0-9_.-]{0,99}')


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec='seconds').replace('+00:00', 'Z')


def _json(value) -> bytes:
    return json.dumps(value, ensure_ascii=False, separators=(',', ':'), allow_nan=False).encode('utf-8')


def _b64(value: bytes) -> str:
    return base64.b64encode(value).decode('ascii')


def _box(key: bytes, plaintext: bytes, aad: str) -> dict:
    iv = secrets.token_bytes(12)
    return {'iv': _b64(iv), 'ct': _b64(AESGCM(key).encrypt(iv, plaintext, aad.encode('utf-8')))}


class LiveProgressEncoder:
    """One fresh AES-256 key per workflow attempt, wrapped for current users."""

    def __init__(self, repository: str, run_id: str, run_attempt: int,
                 master: bytes, users: Mapping[str, dict]):
        if not REPOSITORY_RX.fullmatch(repository):
            raise ValueError('Invalid GitHub repository metadata')
        if not re.fullmatch(r'[0-9]{1,24}', str(run_id)) or int(run_id) < 1:
            raise ValueError('Invalid GitHub run identifier')
        if type(run_attempt) is not int or not 1 <= run_attempt <= 1_000_000:
            raise ValueError('Invalid GitHub run attempt')
        if not isinstance(users, Mapping) or not 1 <= len(users) <= USER_LIMIT:
            raise ValueError('Live progress requires between one and 100 configured vault users')
        self.repository = repository
        self.run_id = str(run_id)
        self.run_attempt = run_attempt
        self._key = secrets.token_bytes(32)
        self._context = f'{repository}:{self.run_id}:{run_attempt}'
        self._users = {}
        for uid, entry in users.items():
            if not re.fullmatch(r'[0-9a-f]{64}', uid):
                raise ValueError('Invalid vault user identifier')
            kek = vault.open_bytes(master, entry['kek_escrow'], 'cc-escrow:' + uid)
            if len(kek) != 32:
                raise ValueError('Invalid vault user key')
            self._users[uid] = _box(kek, self._key, f'cc-live-key:{self._context}:{uid}')

    def _encode(self, progress: dict) -> str:
        raw = _json(progress)
        if len(raw) > RAW_LIMIT:
            raise ValueError('Live progress snapshot exceeds the raw size limit')
        box = _box(self._key, gzip.compress(raw, compresslevel=6, mtime=0), 'cc-live:' + self._context)
        envelope = {'format': FORMAT, 'repository': self.repository,
                    'workflow_run_id': self.run_id, 'run_attempt': self.run_attempt,
                    'generated_at': utc_now(), **box, 'users': self._users}
        return FORMAT + '\n' + _b64(_json(envelope))

    @staticmethod
    def _compact(progress: dict) -> dict:
        result = copy.deepcopy(progress)
        rows = result.get('sources') if isinstance(result.get('sources'), list) else []
        result['source_details_truncated'] = True
        result['source_rows_truncated'] = False
        result['source_rows_total'] = len(rows)
        result['source_rows_included'] = len(rows)

        def compact_row(row):
            if not isinstance(row, dict):
                return {}
            return {str(key)[:80]: value[:180] if isinstance(value, str) and key not in ('id', 'source_id') else value
                    for key, value in row.items()
                    if value is None or isinstance(value, (str, int, float, bool))}

        result['sources'] = [compact_row(row) for row in rows]
        if isinstance(result.get('active_sources'), list):
            result['active_sources'] = [compact_row(row) for row in result['active_sources'][:32]]
        if isinstance(result.get('errors'), list):
            result['errors'] = [str(value)[:200] for value in result['errors'][-5:]]
        for key, value in result.items():
            if isinstance(value, str) and len(value) > 300:
                result[key] = value[:300]
        return result

    def encode(self, progress: dict) -> str:
        if not isinstance(progress, dict):
            raise ValueError('Live progress must be a JSON object')
        if len(_json(progress)) <= RAW_LIMIT:
            text = self._encode(progress)
            if len(text) <= OUTPUT_LIMIT:
                return text
        compact = self._compact(progress)
        rows = compact['sources']
        # Keep every source unless the actual API payload limit requires fewer.
        while True:
            text = self._encode(compact)
            if len(text) <= OUTPUT_LIMIT:
                return text
            if not rows:
                raise ValueError('Encrypted live progress exceeds the Checks output limit')
            rows = sorted(rows, key=lambda row: (
                row.get('state') == 'running',
                str(row.get('finished_at') or row.get('started_at') or ''),
            ), reverse=True)[:len(rows) // 2]
            compact['sources'] = rows
            compact['source_rows_truncated'] = True
            compact['source_rows_included'] = len(rows)


class NullPublisher:
    """No network or key access when optional live publishing is unconfigured."""
    enabled = False

    def publish(self, progress: dict) -> None:
        pass

    def finish(self, *, error: bool = False, cancelled: bool = False) -> bool:
        return False


class GitHubProgressPublisher:
    """A single daemon worker coalesces snapshots; callbacks never do HTTP."""
    enabled = True

    def __init__(self, encoder: LiveProgressEncoder, token: str, head_sha: str, *,
                 session=None, interval_seconds: float = INTERVAL_SECONDS):
        if not token or '\n' in token or '\r' in token:
            raise ValueError('Invalid GitHub progress token')
        if not re.fullmatch(r'[0-9a-fA-F]{40}(?:[0-9a-fA-F]{24})?', head_sha):
            raise ValueError('Invalid GitHub commit metadata')
        self.encoder = encoder
        self._token = token
        self._sha = head_sha
        self._session = session or requests.Session()
        self._interval = max(0.01, interval_seconds)
        self._condition = threading.Condition()
        self._latest: dict | None = None
        self._closing = False
        self._stop = False
        self._error = False
        self._cancelled = False
        self._check_id: int | None = None
        self._creation_attempted = False
        self._finished = False
        self.last_error: str | None = None
        self._started_at = utc_now()
        self._thread = threading.Thread(target=self._worker, name='github-encrypted-progress', daemon=True)
        self._thread.start()

    @property
    def external_id(self) -> str:
        return f'{FORMAT}:{self.encoder.run_id}:{self.encoder.run_attempt}'

    def publish(self, progress: dict) -> None:
        try:
            snapshot = copy.deepcopy(progress)
            if not isinstance(snapshot, dict):
                return
            with self._condition:
                if self._closing or self._stop:
                    return
                self._latest = snapshot  # One slot, never an unbounded queue.
                self._condition.notify()
        except Exception:
            # A malformed optional telemetry value cannot stop collection.
            self.last_error = 'Could not enqueue encrypted progress'

    def _request(self, method: str, path: str, payload: dict | None = None) -> dict:
        response = self._session.request(method, API_ROOT + path, json=payload,
            timeout=REQUEST_TIMEOUT, allow_redirects=False,
            headers={'Authorization': 'Bearer ' + self._token, 'Accept': 'application/vnd.github+json',
                     'X-GitHub-Api-Version': API_VERSION, 'User-Agent': 'CyberCareers-BD-live-progress'})
        if response.status_code not in (200, 201):
            raise ValueError('GitHub did not accept encrypted progress')
        body = response.json()
        if not isinstance(body, dict):
            raise ValueError('Unexpected GitHub progress response')
        return body

    def _recover_check(self) -> None:
        # A timed-out POST can already have created the check. Reconcile its
        # exact run/attempt before retrying creation, avoiding duplicate checks.
        query = urlencode({'check_name': CHECK_NAME, 'filter': 'latest', 'per_page': 100})
        body = self._request('GET', f'/repos/{self.encoder.repository}/commits/{self._sha}/check-runs?{query}')
        candidates = [row['id'] for row in body.get('check_runs', [])
                      if isinstance(row, dict) and row.get('name') == CHECK_NAME
                      and row.get('external_id') == self.external_id and row.get('head_sha') == self._sha
                      and type(row.get('id')) is int and row['id'] > 0]
        if candidates:
            self._check_id = max(candidates)

    def _send(self, progress: dict, final: bool) -> None:
        output = {'title': 'Encrypted collection progress',
                  'summary': 'Sign in to the CyberCareers dashboard to view this collection.',
                  'text': self.encoder.encode(progress)}
        payload = {'status': 'completed' if final else 'in_progress', 'output': output}
        if final:
            status = progress.get('completion_status')
            payload['conclusion'] = ('cancelled' if self._cancelled else
                                     'failure' if self._error or status in ('failed', 'interrupted', 'incomplete') else
                                     'success' if status == 'completed' else 'neutral')
            payload['completed_at'] = utc_now()
        if self._check_id is None and self._creation_attempted:
            self._recover_check()
        if self._check_id is None:
            self._creation_attempted = True
            payload.update(name=CHECK_NAME, head_sha=self._sha, external_id=self.external_id,
                           started_at=self._started_at,
                           details_url=f'https://github.com/{self.encoder.repository}/actions/runs/{self.encoder.run_id}')
            result = self._request('POST', f'/repos/{self.encoder.repository}/check-runs', payload)
            if type(result.get('id')) is not int or result['id'] < 1:
                raise ValueError('GitHub did not return a check identifier')
            self._check_id = result['id']
        else:
            self._request('PATCH', f'/repos/{self.encoder.repository}/check-runs/{self._check_id}', payload)
        self.last_error = None
        if final:
            self._finished = True

    def _worker(self) -> None:
        next_send = 0.0
        try:
            while True:
                with self._condition:
                    while not self._stop and (self._latest is None or
                            not self._closing and time.monotonic() < next_send):
                        delay = None if self._latest is None else max(0.01, next_send - time.monotonic())
                        self._condition.wait(delay)
                    if self._stop:
                        return
                    snapshot = self._latest
                    final = self._closing
                try:
                    self._send(snapshot, final)
                except Exception:
                    # Never log exception bodies, headers, tokens or progress.
                    self.last_error = 'Encrypted live progress is temporarily unavailable'
                    LOG.info('Encrypted live progress update unavailable')
                if final:
                    return
                # Refresh the envelope heartbeat even during a slow source.
                next_send = time.monotonic() + self._interval
        finally:
            close = getattr(self._session, 'close', None)
            if close:
                close()

    def finish(self, *, error: bool = False, cancelled: bool = False) -> bool:
        with self._condition:
            if not self._closing:
                self._error = bool(error)
                self._cancelled = bool(cancelled)
                snapshot = copy.deepcopy(self._latest or {})
                if error or cancelled:
                    snapshot.update(running=False, phase='error', completion_status='interrupted' if cancelled else 'failed',
                                    finished_at=utc_now(), current_source='Collection interrupted')
                elif snapshot.get('running') is not False:
                    # Missing terminal callback is not evidence of completion.
                    snapshot.update(running=False, phase='incomplete', completion_status='incomplete', finished_at=utc_now())
                self._latest = snapshot
                self._closing = True
                self._condition.notify()
        self._thread.join(timeout=FINISH_TIMEOUT)
        if self._thread.is_alive():
            with self._condition:
                self._stop = True
                self._condition.notify()
        return self._finished


def publisher_from_environment(environ: Mapping[str, str] | None = None):
    env = os.environ if environ is None else environ
    required = ('GH_PROGRESS_TOKEN', 'GITHUB_REPOSITORY', 'GITHUB_RUN_ID', 'GITHUB_RUN_ATTEMPT', 'GITHUB_SHA')
    if env.get('GITHUB_ACTIONS', '').lower() != 'true' or any(not env.get(key) for key in required):
        return NullPublisher()
    try:
        encoder = LiveProgressEncoder(env['GITHUB_REPOSITORY'], env['GITHUB_RUN_ID'], int(env['GITHUB_RUN_ATTEMPT']),
                                      vault.load_master(), vault.read_users()['users'])
        return GitHubProgressPublisher(encoder, env['GH_PROGRESS_TOKEN'], env['GITHUB_SHA'])
    except Exception:
        LOG.info('Optional encrypted live progress is not configured')
        return NullPublisher()


def _finish_optional(publisher, *, error=False, cancelled=False) -> None:
    try:
        publisher.finish(error=error, cancelled=cancelled)
    except Exception:
        LOG.info('Optional encrypted live progress could not be finalized')


def main(argv=None) -> int:
    from server.app import load_local_env
    from .collect import run
    load_local_env()
    parser = argparse.ArgumentParser(description='Collect jobs with optional encrypted GitHub live progress')
    parser.add_argument('--max-search-queries', type=int, default=int(os.getenv('MAX_FEED_SEARCHES', '6')))
    parser.add_argument('--max-career-pages', type=int, default=int(os.getenv('MAX_CAREER_PAGES', '250')))
    parser.add_argument('--max-detail-pages', type=int, default=int(os.getenv('MAX_DETAIL_PAGES', '450')))
    parser.add_argument('--dry-run', action='store_true')
    parser.add_argument('--force-feeds', action='store_true')
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format='%(levelname)s %(message)s')
    publisher = NullPublisher() if args.dry_run else publisher_from_environment()
    try:
        result = run(args.max_search_queries, args.max_career_pages, args.max_detail_pages, args.dry_run,
                     force_feeds=args.force_feeds, on_progress=publisher.publish)
    except KeyboardInterrupt:
        _finish_optional(publisher, error=True, cancelled=True)
        return 130
    except Exception:
        _finish_optional(publisher, error=True)
        raise
    else:
        _finish_optional(publisher)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0


if __name__ == '__main__':
    raise SystemExit(main())
