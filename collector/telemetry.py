"""Durable job persistence, source reliability history and refresh telemetry.

This module contains no network calls. Source histories record *attempted checks*
only; scheduled skips and link-only directories are not marked as failures.
Writes are atomic and are usable from both the Python local server and CLI.
"""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable
import json
import threading

HISTORY_LENGTH = 10


def timestamp() -> str:
    return datetime.now(timezone.utc).isoformat(timespec='seconds')


def read_json(path: Path, default: Any) -> Any:
    try:
        return json.loads(path.read_text(encoding='utf-8'))
    except (OSError, ValueError):
        return default


def atomic_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + '.tmp')
    tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    tmp.replace(path)


class CollectionTelemetry:
    """Track per-target outcomes and current-run counts in compact JSON files."""

    def __init__(self, directory: Path, *, total: int, status_callback: Callable[[dict], None] | None = None,
                 persist: bool = True):
        self.directory = directory
        self.persist = persist
        self.callback = status_callback
        self._lock = threading.RLock()
        self.health = read_json(directory / 'source_health.json', {'version': 1, 'sources': {}})
        if not isinstance(self.health, dict):
            self.health = {'version': 1, 'sources': {}}
        self.health.setdefault('sources', {})
        self.progress = {
            'running': True, 'started_at': timestamp(), 'finished_at': None,
            'total': max(0, total), 'checked': 0, 'remaining': max(0, total),
            'succeeded': 0, 'failed': 0, 'partial': 0, 'skipped': 0,
            'jobs_found_this_run': 0, 'new_jobs': 0,
            'current_source': 'Preparing source scans', 'last_checked': None,
            'phase': 'starting', 'errors': [],
        }
        self._write()

    def _write(self) -> None:
        self.progress['remaining'] = max(0, self.progress['total'] - self.progress['checked'])
        # Publish progress first. The browser reads it through the local API.
        if self.persist:
            atomic_json(self.directory / 'progress.json', self.progress)
            self.health['updated_at'] = timestamp()
            atomic_json(self.directory / 'source_health.json', self.health)
        if self.callback:
            self.callback(dict(self.progress))

    def extend_total(self, additional: int) -> None:
        with self._lock:
            self.progress['total'] += max(0, int(additional))
            self._write()

    def phase(self, name: str, current_source: str = '') -> None:
        with self._lock:
            self.progress['phase'] = name
            self.progress['current_source'] = current_source or name
            self._write()

    def completed(self, *, source_id: str, name: str, sector: str, mode: str, state: str,
                  jobs: int = 0, new_jobs: int = 0, message: str = '') -> None:
        """Count one planned target. `cached` and `link-only` aren't attempts."""
        with self._lock:
            state = state.lower()
            if state in ('ok', 'success'):
                outcome = 'success'
                self.progress['succeeded'] += 1
            elif state in ('partial', 'limited', 'degraded'):
                outcome = 'partial'
                self.progress['partial'] += 1
            elif state in ('cached', 'skipped', 'link-only', 'not-due'):
                outcome = 'skipped'
                self.progress['skipped'] += 1
            else:
                outcome = 'failed'
                self.progress['failed'] += 1
            self.progress['checked'] += 1
            self.progress['jobs_found_this_run'] += max(0, int(jobs))
            self.progress['new_jobs'] += max(0, int(new_jobs))
            self.progress['last_checked'] = name
            self.progress['current_source'] = name
            if outcome != 'skipped':
                key = str(source_id or name).strip()
                entry = self.health['sources'].setdefault(key, {
                    'id': key, 'name': name, 'sector': sector, 'mode': mode, 'history': []
                })
                entry.update({'name': name, 'sector': sector, 'mode': mode, 'last_checked_at': timestamp()})
                entry.setdefault('history', []).append({
                    'at': timestamp(), 'result': outcome, 'jobs_found': max(0, int(jobs)),
                    'new_jobs': max(0, int(new_jobs)), 'message': str(message or '')[:240],
                })
                entry['history'] = entry['history'][-HISTORY_LENGTH:]
                entry['successes'] = sum(x['result'] == 'success' for x in entry['history'])
                entry['failures'] = sum(x['result'] == 'failed' for x in entry['history'])
                entry['partial_count'] = sum(x['result'] == 'partial' for x in entry['history'])
                entry['last_result'] = outcome
                entry['jobs_found_last_check'] = max(0, int(jobs))
            self._write()

    def finish(self, *, error: str = '') -> None:
        with self._lock:
            self.progress['running'] = False
            self.progress['finished_at'] = timestamp()
            self.progress['phase'] = 'error' if error else 'completed'
            self.progress['current_source'] = 'Failed' if error else 'All scheduled targets processed'
            if error:
                self.progress['errors'] = [str(error)[:200]]
            self._write()


class IncrementalJobStore:
    """Atomically save richer, deduplicated job data after each source batch."""

    def __init__(self, path: Path, *, persist: bool = True):
        self.path = path
        self.persist = persist
        self.payload = read_json(path, {'jobs': []})
        if not isinstance(self.payload, dict) or not isinstance(self.payload.get('jobs'), list):
            self.payload = {'jobs': []}
        self.jobs: list[dict] = list(self.payload['jobs'])

    def merge_batch(self, incoming: list[dict]) -> int:
        from .collect import deduplicate, similarity_key, today_iso
        if not incoming:
            return 0
        existing = {similarity_key(job) for job in self.jobs}
        fresh_keys = {similarity_key(job) for job in incoming}
        new_count = len(fresh_keys - existing)
        updated = deduplicate(self.jobs + incoming)
        for job in updated:
            if similarity_key(job) in fresh_keys:
                job['last_seen_at'] = today_iso()
        self.jobs = updated
        # One atomic save per provider/target, not one write per feed item.
        self.payload['jobs'] = self.jobs
        self.payload['generated_at'] = timestamp()
        self.payload['data_note'] = ('Persisted incrementally during source checks. Each record retains '
                                     'original source/apply URLs, description and observed metadata; '
                                     'vacancy availability must be confirmed on the publisher page.')
        if self.persist:
            atomic_json(self.path, self.payload)
        return new_count

    def finish(self, jobs: list[dict]) -> None:
        self.jobs = jobs
        self.payload['jobs'] = jobs
        self.payload['generated_at'] = timestamp()
        if self.persist:
            atomic_json(self.path, self.payload)
