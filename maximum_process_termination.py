"""Terminate isolated Maximum worker process groups on policy-limit violations.

This is supervision of the opt-in, trusted PDF subprocess from opener-0306,
not a new inspector, user-selectable command, or file-opening verdict.
"""
import errno
import os
import sys
import selectors
import signal
import subprocess
import sys
import time

from maximum_sanitizer_process import (
    _darwin_group_has_only_zombies,
    _process_has_exited_without_reaping,
    SanitizerProcessExecutionError,
)

MAX_INPUT_BYTES = 16 * 1024 * 1024
MAX_OUTPUT_BYTES = 4096
MAX_WALL_SECONDS = 30
REAP_SECONDS = 3
BLOCK_MESSAGE = "Isolated PDF analysis exceeded process limits; opening was stopped."


class MaximumProcessTerminationError(RuntimeError):
    """Always fixed, path-free error; optional safe category for tests only."""

    _CATEGORIES = frozenset((
        "unknown", "timeout", "worker-exit", "output-limit",
        "transport", "cleanup",
    ))

    def __init__(self, message=BLOCK_MESSAGE, *, category="unknown"):
        super().__init__(BLOCK_MESSAGE)
        self.category = category if category in self._CATEGORIES else "unknown"


def _macos_group_is_zombie_only(pgid):
    """Verify that an EPERM process group has no live members."""
    if sys.platform != "darwin":
        return False
    try:
        result = subprocess.run(
            ("/bin/ps", "-A", "-o", "pgid=,stat="),
            stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL, close_fds=True, cwd="/",
            env={"PATH": "/usr/bin:/bin", "LANG": "C"},
            timeout=2, check=True,
        )
        for line in result.stdout.decode("ascii").splitlines():
            fields = line.split()
            if len(fields) != 2 or not fields[0].isdecimal() or not fields[1]:
                return False
            if int(fields[0]) == pgid and fields[1][0].upper() != "Z":
                return False
        return True
    except (OSError, ValueError, UnicodeDecodeError, subprocess.SubprocessError):
        return False


def _stop_group(process):
    """Stop the isolated process group without ignoring live descendants."""
    try:
        os.killpg(process.pid, signal.SIGKILL)
    except ProcessLookupError:
        if process.poll() is None:
            process.kill()
    except OSError as error:
        # An EPERM group is safe only after its owned leader exited and
        # a complete process snapshot proves no live descendants remain.
        if sys.platform == "darwin" and error.errno == errno.EPERM:
            try:
                if (_process_has_exited_without_reaping(process) and
                        _darwin_group_has_only_zombies(process.pid)):
                    return
            except SanitizerProcessExecutionError:
                pass
        try:
            process.kill()
        except ProcessLookupError:
            pass
        raise MaximumProcessTerminationError(BLOCK_MESSAGE, category="cleanup") from None


def _reap(process):
    try:
        process.wait(timeout=REAP_SECONDS)
    except subprocess.TimeoutExpired:
        try:
            process.kill()
            process.wait(timeout=REAP_SECONDS)
        except (OSError, subprocess.SubprocessError):
            raise MaximumProcessTerminationError(BLOCK_MESSAGE) from None


def run_limited_worker(
    command: tuple[str, ...], contents: bytes, *,
    timeout_seconds: int, environment: dict[str, str],
) -> bytes:
    """Execute trusted worker with a monotonic deadline and bounded pipe reads.

    The caller alone constructs the command and environment; neither is read
    from the PDF. All descendants inherit a dedicated process group. On
    timeout, output overflow, abnormal exit, or even successful completion,
    tear down that group and reap the original child. A descendant cannot
    keep the pipes open past the deadline. stdout is limited *while reading*,
    not after unbounded communicate(). No external PDF data is logged.
    """
    if (os.name != "posix" or
            type(command) is not tuple or len(command) < 2 or
            any(type(arg) is not str or not arg or "\x00" in arg for arg in command) or
            type(contents) is not bytes or not 0 < len(contents) <= MAX_INPUT_BYTES or
            type(timeout_seconds) is not int or not 1 <= timeout_seconds <= MAX_WALL_SECONDS or
            type(environment) is not dict or
            any(type(k) is not str or type(v) is not str
                for k, v in environment.items())):
        raise MaximumProcessTerminationError(BLOCK_MESSAGE)

    process = None
    try:
        process = subprocess.Popen(
            command,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            close_fds=True,
            start_new_session=True,
            cwd="/",
            env=environment,
        )
        deadline = time.monotonic() + timeout_seconds
        output = bytearray()
        position = 0
        with selectors.DefaultSelector() as events:
            os.set_blocking(process.stdin.fileno(), False)
            os.set_blocking(process.stdout.fileno(), False)
            events.register(process.stdin, selectors.EVENT_WRITE)
            events.register(process.stdout, selectors.EVENT_READ)
            while events.get_map():
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise MaximumProcessTerminationError(BLOCK_MESSAGE, category="timeout")
                for key, _ in events.select(timeout=min(remaining, 0.5)):
                    if key.fileobj is process.stdout:
                        # Only consume one byte beyond remaining cumulative
                        # capacity: earlier chunks already occupy the budget.
                        remaining_capacity = MAX_OUTPUT_BYTES - len(output)
                        try:
                            chunk = os.read(process.stdout.fileno(), remaining_capacity + 1)
                        except BlockingIOError:
                            continue
                        if not chunk:
                            events.unregister(process.stdout)
                            process.stdout.close()
                        elif len(output) + len(chunk) > MAX_OUTPUT_BYTES:
                            raise MaximumProcessTerminationError(BLOCK_MESSAGE, category="output-limit")
                        else:
                            output.extend(chunk)
                    else:
                        try:
                            written = os.write(
                                process.stdin.fileno(),
                                memoryview(contents)[position:position + 65536],
                            )
                            position += written
                        except BlockingIOError:
                            continue
                        except BrokenPipeError:
                            position = len(contents)
                        if position == len(contents):
                            events.unregister(process.stdin)
                            process.stdin.close()
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise MaximumProcessTerminationError(BLOCK_MESSAGE)
        # Wait without reaping so the group ID cannot be reassigned before
        # cleanup. Stop every descendant even after the leader exits.
        while not _process_has_exited_without_reaping(process):
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise MaximumProcessTerminationError(
                    BLOCK_MESSAGE, category="timeout",
                )
            time.sleep(min(remaining, 0.025))
        _stop_group(process)
        try:
            return_code = process.wait(timeout=REAP_SECONDS)
        except subprocess.TimeoutExpired:
            raise MaximumProcessTerminationError(
                BLOCK_MESSAGE, category="timeout",
            ) from None
        if return_code != 0:
            raise MaximumProcessTerminationError(
                BLOCK_MESSAGE, category="worker-exit",
            )
        process = None
        return bytes(output)
    except MaximumProcessTerminationError:
        raise
    except (OSError, ValueError, RuntimeError, subprocess.SubprocessError):
        raise MaximumProcessTerminationError(BLOCK_MESSAGE, category="transport") from None
    finally:
        if process is not None:
            try:
                _stop_group(process)
                _reap(process)
            finally:
                if process.stdin is not None and not process.stdin.closed:
                    process.stdin.close()
                if process.stdout is not None and not process.stdout.closed:
                    process.stdout.close()
