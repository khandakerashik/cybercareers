"""Merge previously collected jobs into this release's persistent JSON database.

Usage: python -m collector.import_existing PATH_TO_OLDER_JOBS_JSON
This never sends a file or any data to a third-party service.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from .collect import DATA, annotate_freshness, get_json, valid_url, write_json, job_source_attribution
from .telemetry import IncrementalJobStore


def import_existing_jobs(old_file: Path, *, target: Path | None = None, dry_run: bool = False) -> dict:
    target = target or (DATA / 'jobs.json')
    if old_file.resolve() == target.resolve():
        raise ValueError('Choose an older jobs.json, not the current destination file')
    payload = json.loads(old_file.read_text(encoding='utf-8'))
    candidates = payload.get('jobs', []) if isinstance(payload, dict) else payload
    if not isinstance(candidates, list):
        raise ValueError('Existing file must contain a jobs array')
    accepted = [item for item in candidates if isinstance(item, dict)
                and item.get('company', '').strip().casefold() != 'bangladesh bank'
                and valid_url(item.get('apply_url') or item.get('source_url') or '')
                and item.get('title')]
    for item in accepted:
        origin = job_source_attribution(item.get('source',''), item.get('company',''), item.get('source_url',''))
        item.setdefault('source_name', origin['source_name'])
        item.setdefault('source_domain', origin['source_domain'])
    store = IncrementalJobStore(target, persist=not dry_run)
    previously = len(store.jobs)
    new_count = store.merge_batch(accepted)
    merged = annotate_freshness(store.jobs)
    if not dry_run:
        store.finish(merged)
    return {'accepted_from_old_file': len(accepted), 'previously_stored': previously,
            'added': new_count, 'database_total': len(merged), 'dry_run': dry_run,
            'destination': str(target)}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description='Merge an older CyberCareers BD jobs.json into the current database')
    parser.add_argument('old_jobs_json', type=Path, help='Path to a backup/previous release data/jobs.json')
    parser.add_argument('--dry-run', action='store_true', help='Preview count changes without writing')
    args = parser.parse_args(argv)
    result = import_existing_jobs(args.old_jobs_json, dry_run=args.dry_run)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
