"""Execute the actual inline Actions guards against complete and partial uploads."""
from __future__ import annotations

import ast
import os
import subprocess
import sys
import textwrap
from pathlib import Path

import pytest

pytestmark = pytest.mark.skipif(os.name != 'posix', reason='Exercises inline preflights for the Ubuntu Actions runner')

WORKFLOW = Path(__file__).resolve().parents[1] / '.github' / 'workflows' / 'pages.yml'
INVENTORY = 'Check complete release upload'
COMPATIBILITY = 'Check release compatibility'
PRIVATE_MARKER = 'synthetic-private-value-must-not-appear'


def guard(name):
    step = WORKFLOW.read_text(encoding='utf-8').split('      - name: ' + name + '\n', 1)[1]
    step = step.split('\n      - ', 1)[0]
    shell = textwrap.dedent(step.split('        run: |\n', 1)[1]).splitlines()
    assert shell[0] == "python - <<'PY'" and shell[-1] == 'PY'
    return '\n'.join(shell[1:-1]) + '\n'


def execute(name, directory):
    environment = {**os.environ, 'CC_MASTER_KEY': PRIVATE_MARKER, 'GH_PROGRESS_TOKEN': PRIVATE_MARKER}
    environment.pop('PYTHONPATH', None)
    result = subprocess.run([sys.executable, '-c', guard(name)], cwd=directory,
                            env=environment, capture_output=True, text=True, timeout=15)
    assert PRIVATE_MARKER not in result.stdout + result.stderr
    assert not (directory / 'forbidden-access').exists()
    return result


@pytest.fixture
def release(tmp_path):
    # Derive the inventory from the actual YAML, then supply minimal interfaces.
    # The fixture contains no private key, users file or collected job data.
    assignment = next(node for node in ast.parse(guard(INVENTORY)).body
                      if isinstance(node, ast.Assign) and node.targets[0].id == 'required')
    for name in ast.literal_eval(assignment.value):
        path = tmp_path / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text('' if path.suffix != '.py' else '# Fixture module\n')
    forbidden = (
        "    from pathlib import Path\n"
        "    Path('forbidden-access').write_text('called')\n"
        f"    raise RuntimeError('{PRIVATE_MARKER}')\n"
    )
    (tmp_path / 'collector/collect.py').write_text(
        'def run(max_queries=6, max_career_pages=250, max_detail_pages=450, dry_run=False, *, '
        'force_feeds=False, on_progress=None):\n' + forbidden)
    (tmp_path / 'collector/telemetry.py').write_text(
        'class CollectionTelemetry:\n'
        '    def plan_sources(self, sources): pass\n'
        '    def started(self, **kwargs): pass\n'
        '    def snapshot(self): pass\n')
    for name in ('collector/ci.py', 'collector/github_progress.py', 'vault/backup.py'):
        (tmp_path / name).write_text('def main():\n' + forbidden)
    assets = "('app.js', 'auth.js', 'applications.js', 'github-scan.js')"
    (tmp_path / 'vault/__init__.py').write_text(
        'SITE_FILES = ' + assets + '\n'
        'def load_master():\n' + forbidden +
        'def read_users():\n' + forbidden)
    (tmp_path / 'server/app.py').write_text('PUBLIC_ROOT_FILES = ' + assets + '\n')
    (tmp_path / 'auth.js').write_text('export async function decryptLiveProgress() {}\n')
    (tmp_path / 'app.js').write_text("import {createGitHubScanner} from './github-scan.js?v=5.4.2';\n")
    return tmp_path


def test_complete_release_passes_without_collection_or_key_access(release):
    assert not any((release / name).exists() for name in ('config.js', 'config', 'data', 'encrypted'))
    for name in (INVENTORY, COMPATIBILITY):
        result = execute(name, release)
        assert result.returncode == 0, result.stdout + result.stderr
        assert result.stderr == ''


@pytest.mark.parametrize('missing', ['collector/github_progress.py', 'collector/ci.py', 'github-scan.js'])
def test_partial_upload_names_missing_runtime_before_importing(release, missing):
    (release / missing).unlink()
    # Inventory must not import the collector while diagnosing an upload.
    (release / 'collector/__init__.py').write_text(f"raise RuntimeError('{PRIVATE_MARKER}')\n")
    result = execute(INVENTORY, release)
    assert result.returncode == 1
    assert '::error::Incomplete release upload.' in result.stdout
    assert missing in result.stdout
    assert 'Upload the complete release folders together' in result.stdout
    assert result.stderr == ''


@pytest.mark.parametrize(('path', 'old_code', 'label'), [
    ('collector/telemetry.py', 'class CollectionTelemetry:\n    def snapshot(self): pass\n',
     'source progress interface'),
    ('collector/collect.py', 'def run(): pass\n', 'collector callback interface'),
    ('vault/__init__.py', "SITE_FILES = ('app.js', 'auth.js', 'applications.js')\n", 'vault frontend assets'),
    ('server/app.py', "PUBLIC_ROOT_FILES = ('app.js', 'auth.js', 'applications.js')\n", 'server frontend assets'),
])
def test_mixed_release_interfaces_fail_with_fixed_safe_labels(release, path, old_code, label):
    (release / path).write_text(old_code)
    result = execute(COMPATIBILITY, release)
    assert result.returncode == 1
    assert '::error::Incomplete release upload or incompatible runtime:' in result.stdout
    assert label in result.stdout
    assert result.stderr == ''


def test_failed_import_output_and_exception_details_are_suppressed(release):
    (release / 'collector/github_progress.py').write_text(
        'import os, sys\n'
        f"print('{PRIVATE_MARKER}')\n"
        f"print('{PRIVATE_MARKER}', file=sys.stderr)\n"
        f"os.write(1, b'{PRIVATE_MARKER}')\n"
        f"os.write(2, b'{PRIVATE_MARKER}')\n"
        f"raise RuntimeError('{PRIVATE_MARKER}')\n")
    result = execute(COMPATIBILITY, release)
    assert result.returncode == 1
    assert 'cannot import collector.github_progress' in result.stdout
    assert result.stderr == ''
    assert 'Traceback' not in result.stdout


def test_buffered_native_and_original_stream_output_stays_private(release):
    ctypes = pytest.importorskip('ctypes')
    try:
        getattr(ctypes.CDLL(None), 'printf')
        getattr(ctypes.CDLL(None), 'fflush')
    except (AttributeError, OSError):
        pytest.skip('The current platform does not expose libc output functions')
    (release / 'collector/github_progress.py').write_text(
        'import ctypes, sys\n'
        f"sys.__stdout__.write('{PRIVATE_MARKER}')\n"
        f"sys.__stderr__.write('{PRIVATE_MARKER}')\n"
        f"ctypes.CDLL(None).printf(b'{PRIVATE_MARKER}')\n"
        'def main(): pass\n')
    result = execute(COMPATIBILITY, release)
    assert result.returncode == 0
    assert result.stdout == 'Release runtime interfaces are compatible.\n'
    assert result.stderr == ''


def test_guards_precede_collection_and_workflow_uses_safe_entrypoint():
    workflow = WORKFLOW.read_text(encoding='utf-8')
    assert workflow.index(INVENTORY) < workflow.index('name: Install dependencies')
    assert workflow.index('name: Install dependencies') < workflow.index(COMPATIBILITY)
    assert workflow.index(COMPATIBILITY) < workflow.index('name: Require the vault master key')
    assert workflow.index(COMPATIBILITY) < workflow.index('name: Collect cybersecurity vacancies')
    assert 'run: python -m collector.ci\n' in workflow
    assert 'python -m collector.github_progress > /dev/null' not in workflow
