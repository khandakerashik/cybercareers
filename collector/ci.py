"""Public-log-safe CI entry point for the normal GitHub collection CLI.

Collector output goes to the null device, never a temporary trace file. Only
fixed failure categories and explicitly approved code locations are public.
Importing this module does not load collector state, credentials or publishers.
"""
from __future__ import annotations

import contextlib
import logging
import os
from pathlib import Path
import sys


_ROOT = Path(__file__).resolve().parents[1]
_PUBLIC_FILES = (
    'collector/ci.py', 'collector/github_progress.py', 'collector/collect.py',
    'collector/telemetry.py', 'collector/relevance.py', 'collector/vacancy.py',
    'collector/ats.py', 'collector/robots.py', 'collector/render.py',
    'collector/textmine.py',
    'collector/free_feeds.py', 'collector/custom_feeds.py',
    'collector/email_alerts.py', 'collector/search_apis.py',
    'collector/__init__.py', 'server/app.py', 'server/__init__.py',
    'vault/__init__.py',
)
_PUBLIC_PATHS = {str(_ROOT / name): name for name in _PUBLIC_FILES}
_PUBLIC_ERRORS = (
    ModuleNotFoundError, ImportError, SyntaxError, FileNotFoundError,
    PermissionError, TimeoutError, ConnectionError, OSError, ValueError,
    TypeError, AttributeError, KeyError, IndexError, RecursionError,
    RuntimeError, MemoryError, AssertionError,
)


def _flush_streams(*streams) -> None:
    for stream in streams:
        try:
            stream.flush()
        except BaseException:
            pass  # Cleanup must continue even if a stream was closed/replaced.


def _flush_native() -> None:
    # A native printf may still be buffered when main returns. Flush it while
    # fds 1/2 still point to the null device, before restoring public output.
    try:
        import ctypes
        flush = ctypes.CDLL(None).fflush
        flush.argtypes = [ctypes.c_void_p]
        flush.restype = ctypes.c_int
        flush(None)
    except (ImportError, AttributeError, OSError):
        pass


def _restore_fd(target: int, saved: int) -> None:
    try:
        os.dup2(saved, target)
    finally:
        os.close(saved)


@contextlib.contextmanager
def _private_output():
    original_out, original_err = sys.stdout, sys.stderr
    _flush_streams(original_out, original_err)
    with open(os.devnull, 'w', encoding='utf-8') as sink, contextlib.ExitStack() as stack:
        # dup descriptors are non-inheritable. Child processes inherit only
        # the redirected standard descriptors, not handles to public logs.
        for target in (1, 2):
            saved = os.dup(target)
            stack.callback(_restore_fd, target, saved)
            os.dup2(sink.fileno(), target)
        previous_disable = logging.root.manager.disable
        stack.callback(logging.disable, previous_disable)
        logging.disable(sys.maxsize)
        stack.enter_context(contextlib.redirect_stdout(sink))
        stack.enter_context(contextlib.redirect_stderr(sink))
        try:
            yield
        finally:
            _flush_streams(sys.stdout, sys.stderr, original_out, original_err, sink)
            _flush_native()


def _exit_status(value) -> int:
    if value is None:
        return 0
    if type(value) is bool:
        return int(value)
    # In particular, 256 must not become a successful shell exit via modulo.
    return value if type(value) is int and 0 <= value <= 255 else 1


def _public_location(error: BaseException) -> tuple[str, int] | None:
    # Do not use traceback.format_exc, source lines, function names, exception
    # filenames or locals. Even a SyntaxError can carry private source text.
    frame = BaseException.__traceback__.__get__(error)
    location = None
    while frame is not None:
        name = _PUBLIC_PATHS.get(frame.tb_frame.f_code.co_filename)
        if name is not None and 1 <= frame.tb_lineno <= 10_000_000:
            location = (name, frame.tb_lineno)
        frame = frame.tb_next
    return location


def _public_failure(error: BaseException) -> tuple[int, str, tuple[str, int] | None]:
    if isinstance(error, KeyboardInterrupt):
        code, category = 130, 'KeyboardInterrupt'
    elif isinstance(error, SystemExit):
        # Read the built-in field without calling str/int on an arbitrary value.
        code, category = _exit_status(SystemExit.code.__get__(error)), 'SystemExit'
    else:
        code = 1
        category = next((kind.__name__ for kind in _PUBLIC_ERRORS if isinstance(error, kind)), 'UnexpectedError')
    return code, category, _public_location(error)


def main(argv=None) -> int:
    code, category, location = 1, 'UnexpectedError', None
    try:
        with _private_output():
            try:
                from .github_progress import main as collect
                code = _exit_status(collect(argv))
                category = 'KeyboardInterrupt' if code == 130 else 'ExitStatus'
            except BaseException as error:
                code, category, location = _public_failure(error)
    except BaseException as error:
        # Setup/cleanup failures are also sanitized, and collection is never
        # started if its output cannot first be redirected.
        code, category, location = _public_failure(error)
    try:
        if code == 0:
            print('Collection completed successfully.', flush=True)
        else:
            attributes = f'file={location[0]},line={location[1]},' if location else ''
            print(f'::error {attributes}title=Collection failed::Collection failed ({category}). '
                  'Private diagnostic details were suppressed.', flush=True)
    except OSError:
        return code or 1
    return code


if __name__ == '__main__':
    raise SystemExit(main())
