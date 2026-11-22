"""Durable job persistence, source reliability history and refresh telemetry.

This module contains no network calls. Source histories record *attempted checks*
only; scheduled skips and link-only directories are not marked as failures.
Writes are atomic and are usable from both the Python local server and CLI.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable
import copy
import json
import logging
import threading
import os
import uuid

HISTORY_LENGTH = 10
LOG = logging.getLogger(__name__)
TERMINAL_SOURCE_STATES = frozenset({'success', 'partial', 'failed', 'skipped'})


def collection_schedule(now: datetime | None = None) -> dict:
    """Describe the scheduler that actually exists; a one-off CLI is not hourly."""
    now = now or datetime.now(timezone.utc)
    if os.environ.get('GITHUB_ACTIONS', '').lower() == 'true':
        upcoming = now.replace(minute=12, second=0, microsecond=0)
        if upcoming <= now:
            upcoming += timedelta(hours=1)
        return {'mode': 'github_actions', 'enabled': True, 'interval_minutes': 60,
                'next_scheduled_at': upcoming.isoformat(timespec='seconds'),
                'note': 'Hourly at minute 12; GitHub Actions may delay or skip a scheduled run.'}
    return {'mode': 'manual', 'enabled': False, 'interval_minutes': None,
            'next_scheduled_at': None, 'note': 'One-off collection; no scheduler is running.'}


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


def source_started(on_source, source: dict) -> None:
    """Optional start hook on the existing result callback, before network I/O.

    Old callbacks taking only ``(outcome, jobs)`` need no signature changes.
    Progress observers are advisory and may never stop source collection.
    """
    callback = getattr(on_source, 'started', None) if on_source else None
    if callback:
        try:
            callback(copy.deepcopy(source))
        except Exception as exc:
            LOG.warning('Source-start observer failed (%s); collection continues', type(exc).__name__)


def _elapsed(started: str | None, finished: str) -> float | None:
    if not started:
        return None
    try:
        return max(0, round((datetime.fromisoformat(finished) - datetime.fromisoformat(started)).total_seconds(), 1))
    except (TypeError, ValueError):
        return None


class CollectionTelemetry:
    """Track per-target outcomes and current-run counts in compact JSON files."""

    def __init__(self, directory: Path, *, total: int, status_callback: Callable[[dict], None] | None = None,
                 persist: bool = True, schedule: dict | None = None):
        self.directory = directory
        self.persist = persist
        self.callback = status_callback
        self._lock = threading.RLock()
        self._source_index: dict[str, dict] = {}
        self._lifecycle = False
        self._phase_message = 'Preparing source scans'
        self.health = read_json(directory / 'source_health.json', {'version': 1, 'sources': {}})
        if not isinstance(self.health, dict):
            self.health = {'version': 1, 'sources': {}}
        self.health.setdefault('sources', {})
        previous = read_json(directory / 'progress.json', {})
        status = read_json(directory / 'status.json', {})
        previous = previous if isinstance(previous, dict) else {}
        status = status if isinstance(status, dict) else {}
        completed = previous.get('last_completed_at') or status.get('last_completed_at')
        if not completed and previous.get('phase') == 'completed':
            completed = previous.get('finished_at')
        self.progress = {
            'run_id': uuid.uuid4().hex,
            'running': True, 'started_at': timestamp(), 'finished_at': None,
            'updated_at': timestamp(), 'sources': [], 'active_sources': [],
            'last_completed_at': completed,
            'last_successful_at': previous.get('last_successful_at') or status.get('last_successful_at'),
            'completion_status': 'running', 'duration_seconds': None,
            'schedule': dict(schedule) if schedule is not None else collection_schedule(),
            'total': max(0, total), 'checked': 0, 'remaining': max(0, total),
            'succeeded': 0, 'failed': 0, 'partial': 0, 'skipped': 0,
            'jobs_found_this_run': 0, 'new_jobs': 0,
            'current_source': 'Preparing source scans', 'last_checked': None,
            'phase': 'starting', 'errors': [],
            'previous_errors': copy.deepcopy(previous.get('errors') or status.get('errors') or []),
        }
        self._write()

    def _write(self) -> None:
        self.progress['updated_at'] = timestamp()
        self.progress['total'] = max(self.progress['total'], len(self._source_index))
        self.progress['remaining'] = max(0, self.progress['total'] - self.progress['checked'])
        active = [row for row in self.progress['sources'] if row['state'] == 'running']
        self.progress['active_sources'] = copy.deepcopy(active)
        if self.progress['running']:
            names = [row['name'] for row in active]
            self.progress['current_source'] = (' · '.join(names[:3]) + (f' · +{len(names)-3} more' if len(names)>3 else '')) if names else self._phase_message
        # Publish progress first. The browser reads it through the local API.
        if self.persist:
            atomic_json(self.directory / 'progress.json', self.progress)
            self.health['updated_at'] = timestamp()
            atomic_json(self.directory / 'source_health.json', self.health)
        if self.callback:
            try:
                self.callback(copy.deepcopy(self.progress))
            except Exception as exc:
                LOG.warning('Progress observer failed (%s); collection continues', type(exc).__name__)

    def snapshot(self) -> dict:
        """An independent snapshot safe for HTTP, async publishers and tests."""
        with self._lock:
            return copy.deepcopy(self.progress)

    def _source(self, source_id: str, name: str = '', sector: str = '', mode: str = '') -> dict:
        key = str(source_id or name or 'unknown').strip()
        row = self._source_index.get(key)
        if row is None:
            row = {'id': key, 'name': str(name or key), 'sector': str(sector or 'Other'),
                   'mode': str(mode or 'unknown'), 'state': 'queued', 'started_at': None,
                   'finished_at': None, 'duration_seconds': None, 'jobs_found': 0,
                   'new_jobs': 0, 'message': 'Waiting for scheduled check'}
            self._source_index[key] = row
            self.progress['sources'].append(row)
        else:
            for field, value in (('name', name), ('sector', sector), ('mode', mode)):
                if value:
                    row[field] = str(value)
        return row

    def plan_sources(self, sources: list[dict]) -> None:
        """Queue known/dynamically discovered targets without counting duplicates."""
        with self._lock:
            self._lifecycle = True
            for source in sources:
                if not isinstance(source, dict):
                    continue
                self._source(source.get('source_id') or source.get('id') or source.get('name'),
                             source.get('name', ''), source.get('sector', ''), source.get('mode', ''))
            self._write()

    def started(self, *, source_id: str, name: str, sector: str = 'Other', mode: str = 'unknown',
                message: str = '') -> None:
        """Mark a source running immediately before its first external operation."""
        with self._lock:
            self._lifecycle = True
            row = self._source(source_id, name, sector, mode)
            if row['state'] in TERMINAL_SOURCE_STATES or row['state'] == 'running':
                return
            row.update(state='running', started_at=timestamp(), finished_at=None, duration_seconds=None,
                       message=str(message or 'Checking source')[:240])
            self._write()

    def extend_total(self, additional: int) -> None:
        with self._lock:
            self.progress['total'] += max(0, int(additional))
            self._write()

    def phase(self, name: str, current_source: str = '') -> None:
        with self._lock:
            self.progress['phase'] = name
            self._phase_message = current_source or name
            self._write()

    def completed(self, *, source_id: str, name: str, sector: str, mode: str, state: str,
                  jobs: int = 0, new_jobs: int = 0, message: str = '', **details) -> None:
        """Count one planned target. `cached` and `link-only` aren't attempts."""
        with self._lock:
            row = self._source(source_id, name, sector, mode)
            if self._lifecycle and row['state'] in TERMINAL_SOURCE_STATES:
                return
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
            finished = timestamp()
            row.update(state=outcome, finished_at=finished,
                       duration_seconds=_elapsed(row.get('started_at'), finished),
                       jobs_found=max(0, int(jobs)), new_jobs=max(0, int(new_jobs)),
                       message=str(message or ('Not due; cached data retained' if outcome == 'skipped' else 'Check completed'))[:240])
            if outcome != 'skipped':
                key = str(source_id or name).strip()
                entry = self.health['sources'].setdefault(key, {
                    'id': key, 'name': name, 'sector': sector, 'mode': mode, 'history': []
                })
                entry.update({'name': name, 'sector': sector, 'mode': mode, 'last_checked_at': timestamp()})
                diagnostic = {key: details[key] for key in (
                    'reason_code', 'resolved_url', 'checked_url', 'recovery_hint',
                    'rejected_count', 'raw_jobs_found', 'requests', 'coverage_limited',
                    'checked_urls', 'listing_pages', 'collection_complete',
                ) if details.get(key) is not None}
                row.update(copy.deepcopy(diagnostic))
                entry.update(diagnostic)
                entry.setdefault('history', []).append({
                    'at': timestamp(), 'result': outcome, 'jobs_found': max(0, int(jobs)),
                    'new_jobs': max(0, int(new_jobs)), 'message': str(message or '')[:240],
                    **diagnostic,
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
            incomplete = self.progress['checked'] < self.progress['total'] or any(
                row['state'] in ('queued', 'running') for row in self.progress['sources'])
            # A stopped run must not leave sources visibly running forever.
            # Queued sources remain unattempted; never count them as fetched.
            for row in self.progress['sources']:
                if row['state'] == 'running':
                    self.completed(source_id=row['id'], name=row['name'], sector=row['sector'], mode=row['mode'],
                                   state='failed', message='Collection interrupted before this source returned a result')
                elif row['state'] == 'queued':
                    row['message'] = 'Not reached before collection stopped'
            self.progress['running'] = False
            self.progress['finished_at'] = timestamp()
            if self.progress.get('schedule', {}).get('mode') == 'github_actions':
                self.progress['schedule'] = collection_schedule(datetime.fromisoformat(self.progress['finished_at']))
            try:
                self.progress['duration_seconds'] = max(0, round((
                    datetime.fromisoformat(self.progress['finished_at']) -
                    datetime.fromisoformat(self.progress['started_at'])).total_seconds(), 1))
            except (ValueError, TypeError):
                self.progress['duration_seconds'] = None
            issues = bool(self.progress['failed'] or self.progress['partial'] or incomplete)
            self.progress['completion_status'] = 'failed' if error else ('incomplete' if incomplete else ('completed_with_issues' if issues else 'completed'))
            self.progress['phase'] = 'error' if error else ('incomplete' if incomplete else 'completed')
            self.progress['current_source'] = 'Failed' if error else ('Some scheduled targets were not processed' if incomplete else 'All scheduled targets processed')
            if error:
                if str(error)[:200] not in self.progress['errors']:
                    self.progress['errors'].append(str(error)[:200])
            elif not incomplete:
                self.progress['last_completed_at'] = self.progress['finished_at']
                if not issues:
                    self.progress['last_successful_at'] = self.progress['finished_at']
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
        from .collect import deduplicate, similarity_key
        if not incoming:
            return 0
        existing = {similarity_key(job) for job in self.jobs}
        fresh_keys = {similarity_key(job) for job in incoming}
        new_count = len(fresh_keys - existing)
        updated = deduplicate(self.jobs + incoming)
        # Each adapter supplies its observation date. Re-reading an older
        # alert from the mailbox backlog must not make its vacancy look new.
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
