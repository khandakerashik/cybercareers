"""Subprocess privacy checks; never invoke real collection, keys or network."""
from pathlib import Path
import os
import re
import shutil
import subprocess
import sys
import textwrap

import pytest

from collector import ci

pytestmark = pytest.mark.skipif(os.name != 'posix', reason='Exercises the Ubuntu Actions file-descriptor and native-output boundary')


SECRET = 'PRIVATE_TOKEN_JOB_AND_EXCEPTION_VALUE_59d012'
SUCCESS = 'Collection completed successfully.\n'
ANNOTATION = re.compile(
    r'::error (?:file=(?:collector/(?:ci|github_progress)\.py),line=[1-9][0-9]*,)?'
    r'title=Collection failed::Collection failed \([A-Za-z]+\)\. '
    r'Private diagnostic details were suppressed\.\n\Z'
)


def fixture_package(tmp_path, body=None):
    package = tmp_path / 'collector'
    package.mkdir()
    (package / '__init__.py').write_text('')
    shutil.copy2(ci.__file__, package / 'ci.py')
    if body is not None:
        (package / 'github_progress.py').write_text(textwrap.dedent(body))
    return tmp_path


def run_fixture(root, *, arguments=(), bootstrap=None):
    command = ([sys.executable, '-c', bootstrap] if bootstrap is not None
               else [sys.executable, '-m', 'collector.ci', *arguments])
    return subprocess.run(command, cwd=root, capture_output=True, text=True, timeout=15)


def assert_private(result):
    assert SECRET not in result.stdout + result.stderr
    assert 'Traceback' not in result.stdout + result.stderr


def test_cli_suppresses_import_print_logging_native_and_child_output(tmp_path):
    root = fixture_package(tmp_path, f'''
        import ctypes, logging, os, subprocess, sys
        secret = {SECRET!r}
        print(secret)
        logging.critical(secret)
        def main(argv=None):
            assert argv is None
            assert sys.argv[1:] == ['--max-search-queries', '0', '--dry-run']
            print(secret, file=sys.stderr)
            logging.getLogger('private').log(100, secret)
            os.write(1, secret.encode())
            os.write(2, secret.encode())
            sys.__stdout__.write(secret)
            sys.__stderr__.write(secret)
            ctypes.CDLL(None).printf(secret.encode())
            subprocess.run([sys.executable, '-c', 'import os; os.write(1, ' + repr(secret.encode()) + '); os.write(2, ' + repr(secret.encode()) + ')'], check=True)
            return 0
    ''')
    result = run_fixture(root, arguments=('--max-search-queries', '0', '--dry-run'))
    assert result.returncode == 0
    assert result.stdout == SUCCESS
    assert result.stderr == ''
    assert_private(result)


@pytest.mark.parametrize('body,category,frame', [
    (None, 'ModuleNotFoundError', 'collector/ci.py'),
    (f'print({SECRET!r})\nraise ImportError({SECRET!r})', 'ImportError', 'collector/github_progress.py'),
    (f'def main(:  # {SECRET}', 'SyntaxError', 'collector/ci.py'),
    (f'def main(argv=None):\n    raise ValueError({SECRET!r})', 'ValueError', 'collector/github_progress.py'),
    (f'def main(argv=None):\n    raise type({SECRET!r}, (Exception,), {{}})({SECRET!r})', 'UnexpectedError', 'collector/github_progress.py'),
])
def test_failures_expose_only_fixed_category_and_approved_frame(tmp_path, body, category, frame):
    result = run_fixture(fixture_package(tmp_path, body))
    assert result.returncode == 1
    assert ANNOTATION.fullmatch(result.stdout)
    assert f'file={frame},line=' in result.stdout
    assert f'({category})' in result.stdout
    assert result.stderr == ''
    assert_private(result)


def test_exception_chain_source_and_arbitrary_filename_are_not_public(tmp_path):
    root = fixture_package(tmp_path, f'''
        import logging, warnings
        def main(argv=None):
            warnings.warn({SECRET!r})
            try:
                exec(compile('raise ValueError(' + repr({SECRET!r}) + ')', '/tmp/' + {SECRET!r} + '.py', 'exec'))
            except ValueError as error:
                logging.exception({SECRET!r})
                raise RuntimeError({SECRET!r}) from error
    ''')
    result = run_fixture(root)
    assert result.returncode == 1
    assert ANNOTATION.fullmatch(result.stdout)
    assert '(RuntimeError)' in result.stdout
    assert result.stderr == ''
    assert_private(result)


@pytest.mark.parametrize('value,expected', [('0', 0), ('None', 0), ('2', 2), ('130', 130),
                                            ('256', 1), ('-1', 1), (repr(SECRET), 1)])
def test_system_exit_preserves_safe_numeric_status_without_printing_its_value(tmp_path, value, expected):
    root = fixture_package(tmp_path, f'''
        import sys
        def main(argv=None):
            print({SECRET!r}, file=sys.stderr)
            raise SystemExit({value})
    ''')
    result = run_fixture(root)
    assert result.returncode == expected
    assert result.stdout == SUCCESS if expected == 0 else ANNOTATION.fullmatch(result.stdout)
    if expected:
        assert '(SystemExit)' in result.stdout
    assert result.stderr == ''
    assert_private(result)


@pytest.mark.parametrize('body', ['raise KeyboardInterrupt()', 'return 130'])
def test_interrupt_is_nonzero_and_private(tmp_path, body):
    root = fixture_package(tmp_path, f'def main(argv=None):\n    {body}\n')
    result = run_fixture(root)
    assert result.returncode == 130
    assert ANNOTATION.fullmatch(result.stdout)
    assert '(KeyboardInterrupt)' in result.stdout
    assert result.stderr == ''


def test_streams_descriptors_and_prior_logging_threshold_are_restored_after_failure(tmp_path):
    root = fixture_package(tmp_path, f'''
        import ctypes, logging, os, sys
        def main(argv=None):
            assert argv == ['--dry-run']
            print({SECRET!r})
            ctypes.CDLL(None).printf({SECRET.encode()!r})
            logging.critical({SECRET!r})
            raise ValueError({SECRET!r})
    ''')
    bootstrap = textwrap.dedent('''
        import logging, os, sys
        from collector.ci import main
        original = (sys.stdout, sys.stderr)
        logging.basicConfig(level=logging.INFO)
        logging.disable(25)
        code = main(['--dry-run'])
        assert (sys.stdout, sys.stderr) == original
        assert logging.root.manager.disable == 25
        os.write(1, b'FD1_RESTORED\\n')
        os.write(2, b'FD2_RESTORED\\n')
        print('PYTHON_RESTORED')
        logging.warning('LOGGING_RESTORED')
        raise SystemExit(code)
    ''')
    result = run_fixture(root, bootstrap=bootstrap)
    assert result.returncode == 1
    assert 'FD1_RESTORED' in result.stdout and 'PYTHON_RESTORED' in result.stdout
    assert 'FD2_RESTORED' in result.stderr and 'LOGGING_RESTORED' in result.stderr
    assert_private(result)


def test_no_approved_frame_has_a_stable_generic_fallback():
    try:
        exec(compile(f'raise ValueError({SECRET!r})', f'collector/{SECRET}.py', 'exec'))
    except ValueError as error:
        code, category, location = ci._public_failure(error)
    assert (code, category, location) == (1, 'ValueError', None)


def test_import_does_not_import_the_collector_or_change_logging(tmp_path):
    root = fixture_package(tmp_path, f'raise RuntimeError({SECRET!r})')
    result = run_fixture(root, bootstrap='import logging, sys; before=logging.root.manager.disable; import collector.ci; assert "collector.github_progress" not in sys.modules; assert logging.root.manager.disable==before')
    assert result.returncode == 0
    assert result.stdout == result.stderr == ''
