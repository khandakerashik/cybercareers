"""Tests never depend on live collected data.

data/jobs.json is git-ignored (published only encrypted), so a fresh CI checkout
may not have it. The local-server tests need a file to serve: use the bundled
sample and remove it afterwards if it was not there before.
"""
import shutil
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / 'tests' / 'fixtures' / 'seed_jobs.json'


@pytest.fixture(scope='session', autouse=True)
def sample_dataset_if_missing():
    created = []
    for name, src in (('jobs.json', FIXTURE),):
        target = ROOT / 'data' / name
        if not target.exists():
            shutil.copy(src, target)
            created.append(target)
    for name, body in (('status.json', '{}\n'), ('source_health.json', '{"sources": {}}\n'), ('progress.json', '{}\n')):
        target = ROOT / 'data' / name
        if not target.exists():
            target.write_text(body, encoding='utf-8')
            created.append(target)
    yield
    for path in created:
        path.unlink(missing_ok=True)
