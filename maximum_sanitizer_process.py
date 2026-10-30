"""Hard wall-time and process-tree limits for the optional Maximum PDF converter.

This is a passive sanitization primitive. It never scans, saves, opens, or
authorizes a PDF; failure to complete within the deadline returns no output.
"""
import errno
import os
from pathlib import Path
import selectors
import signal
import stat
import subprocess
import sys
import time

MAX_INPUT_BYTES = 16 * 1024 * 1024
MAX_OUTPUT_BYTES = 32 * 1024 * 1024
MAX_WALL_SECONDS = 45
MAX_SANITIZER_MEMORY_BYTES = 1024 * 1024 * 1024
MEMORY_POLL_INTERVAL_SECONDS = 0.05
MEMORY_LIMIT_SETUP_FAILED_EXIT_CODE = 125
REAP_TIMEOUT_SECONDS = 3
READ_CHUNK_BYTES = 65536
BLOCK_MESSAGE = "PDF sanitization exceeded execution limits; no copy was offered."
TIMEOUT_MESSAGE = "PDF sanitization exceeded its execution deadline; no copy was offered."
OUTPUT_LIMIT_MESSAGE = "PDF sanitization exceeded its output limit; no copy was offered."
MEMORY_LIMIT_MESSAGE = (
    "PDF sanitization exceeded or could not verify its memory limit; no copy was offered."
)


class SanitizerProcessExecutionError(RuntimeError):
    """Fixed, path-free failure to supervise the sanitizer process."""


class SanitizerProcessTimedOut(SanitizerProcessExecutionError):
    """The converter or an inherited output-pipe descendant exceeded its deadline."""


class SanitizerProcessOutputLimitExceeded(SanitizerProcessExecutionError):
    """The converter produced more bytes than the output budget."""


class SanitizerProcessMemoryLimitError(SanitizerProcessExecutionError):
    """The converter exceeded its memory ceiling or the ceiling could not be verified."""


def _memory_limited_command(command: tuple[str, ...]) -> tuple[str, ...]:
    """Apply a Linux address-space limit or require the macOS RSS watchdog."""
    if sys.platform == "linux":
        try:
            source = Path(__file__).resolve(strict=True)
            launcher = source.with_name("maximum_sanitizer_memory_launcher.py")
            if launcher.is_symlink() or launcher.resolve(strict=True) != launcher:
                raise OSError
            info = launcher.lstat()
            if (
                not stat.S_ISREG(info.st_mode)
                or info.st_mode & (stat.S_IWGRP | stat.S_IWOTH)
                or info.st_uid not in (0, os.geteuid())
                or not os.access(launcher, os.R_OK)
            ):
                raise OSError
            python = str(Path(sys.executable).resolve(strict=True))
            if not os.path.isabs(python) or not os.access(python, os.X_OK):
                raise OSError
            if not os.path.isdir("/proc") or not os.access("/proc", os.R_OK | os.X_OK):
                raise OSError
            return (python, "-I", "-B", str(launcher), "--", *command)
        except (OSError, RuntimeError, TypeError, ValueError):
            raise SanitizerProcessMemoryLimitError(MEMORY_LIMIT_MESSAGE) from None
    if sys.platform == "darwin":
        if not os.path.isfile("/bin/ps") or not os.access("/bin/ps", os.X_OK):
            raise SanitizerProcessMemoryLimitError(MEMORY_LIMIT_MESSAGE)
        return command
    raise SanitizerProcessMemoryLimitError(MEMORY_LIMIT_MESSAGE)


def _linux_process_group_memory_bytes(process_group_id: int, *, allow_empty: bool) -> int:
    """Sum resident pages for a Linux process group using trusted procfs data."""
    try:
        page_size = os.sysconf("SC_PAGE_SIZE")
        if type(page_size) is not int or page_size <= 0:
            raise OSError
        total = 0
        found = False
        with os.scandir("/proc") as entries:
            for entry in entries:
                if not entry.name.isdecimal():
                    continue
                pid = int(entry.name)
                member = False
                try:
                    with open(f"/proc/{pid}/stat", "rb") as stream:
                        record = stream.read()
                    closing = record.rfind(b")")
                    if closing < 0:
                        raise ValueError
                    fields = record[closing + 2:].split()
                    if len(fields) < 3:
                        raise ValueError
                    if int(fields[2]) != process_group_id:
                        continue
                    member = True
                    with open(f"/proc/{pid}/statm", "rb") as stream:
                        memory_fields = stream.read().split()
                    if len(memory_fields) < 2:
                        raise ValueError
                    resident_pages = int(memory_fields[1])
                    if resident_pages < 0:
                        raise ValueError
                    total += resident_pages * page_size
                    found = True
                except FileNotFoundError:
                    # A process may exit between the /proc directory listing
                    # and reading its status; the next poll sees the final group.
                    continue
                except PermissionError:
                    if member or pid == process_group_id:
                        raise
                    continue
                except (OSError, ValueError, IndexError):
                    if member or pid == process_group_id:
                        raise
                    continue
        if not found and not allow_empty:
            raise OSError
        return total
    except (OSError, ValueError, OverflowError):
        raise SanitizerProcessMemoryLimitError(MEMORY_LIMIT_MESSAGE) from None


def _darwin_process_group_memory_bytes(
    process_group_id: int, *, allow_empty: bool, timeout_seconds: float,
) -> int:
    """Sum macOS process-group RSS; failed or malformed probes fail closed."""
    try:
        deadline = time.monotonic() + max(0.001, timeout_seconds)
        timeout = max(0.001, min(timeout_seconds, 0.25))
        completed = subprocess.run(
            ("/bin/ps", "-o", "rss=", "-g", str(process_group_id)),
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            close_fds=True,
            cwd="/",
            env={"PATH": "/usr/bin:/bin", "LANG": "C"},
            timeout=timeout,
            check=False,
        )
        if completed.returncode == 0:
            values = []
            for line in completed.stdout.decode("ascii").splitlines():
                if not line.strip():
                    continue
                value = line.strip()
                if not value.isdecimal():
                    raise ValueError
                values.append(int(value))
            if values:
                # ps reports RSS in KiB on macOS.
                return sum(values) * 1024
            if not allow_empty:
                raise OSError
        elif not allow_empty:
            raise OSError

        # A process can exit between the wait-status check and the targeted
        # ps snapshot. Verify that the process group is truly gone and that
        # the monitoring command itself still works before accepting zero.
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise subprocess.TimeoutExpired("/bin/ps", timeout_seconds)
        completed = subprocess.run(
            ("/bin/ps", "-A", "-o", "pid=,pgid=,rss="),
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            close_fds=True,
            cwd="/",
            env={"PATH": "/usr/bin:/bin", "LANG": "C"},
            timeout=max(0.001, min(remaining, 0.25)),
            check=True,
        )
        total_kib = 0
        found = False
        for line in completed.stdout.decode("ascii").splitlines():
            if not line.strip():
                continue
            fields = line.split()
            if (len(fields) != 3 or not fields[0].isdecimal()
                    or not fields[1].isdecimal()):
                raise ValueError
            if int(fields[1]) != process_group_id:
                continue
            if not fields[2].isdecimal():
                raise ValueError
            total_kib += int(fields[2])
            found = True
        if found:
            return total_kib * 1024
        if not allow_empty:
            raise OSError
        return 0
    except (OSError, ValueError, UnicodeDecodeError, subprocess.SubprocessError):
        raise SanitizerProcessMemoryLimitError(MEMORY_LIMIT_MESSAGE) from None


def _process_group_memory_bytes(
    process_group_id: int, *, allow_empty: bool, timeout_seconds: float,
) -> int:
    """Measure aggregate process-group RSS without trusting converter output."""
    if type(process_group_id) is not int or process_group_id <= 0:
        raise SanitizerProcessMemoryLimitError(MEMORY_LIMIT_MESSAGE)
    if sys.platform == "linux":
        return _linux_process_group_memory_bytes(process_group_id, allow_empty=allow_empty)
    if sys.platform == "darwin":
        return _darwin_process_group_memory_bytes(
            process_group_id, allow_empty=allow_empty, timeout_seconds=timeout_seconds,
        )
    raise SanitizerProcessMemoryLimitError(MEMORY_LIMIT_MESSAGE)


def _process_has_exited_without_reaping(process) -> bool:
    """Detect child exit while retaining its PID until process-group cleanup."""
    if process.returncode is not None:
        return True
    if sys.platform == "linux":
        if (
            callable(getattr(os, "waitid", None))
            and all(hasattr(os, name) for name in ("P_PID", "WEXITED", "WNOHANG", "WNOWAIT"))
        ):
            try:
                result = os.waitid(
                    os.P_PID, process.pid, os.WEXITED | os.WNOHANG | os.WNOWAIT,
                )
            except (AttributeError, ChildProcessError, OSError, ValueError):
                raise SanitizerProcessExecutionError(BLOCK_MESSAGE) from None
            return result is not None and result.si_pid != 0
        try:
            with open(f"/proc/{process.pid}/stat", "rb") as stream:
                record = stream.read()
            closing = record.rfind(b")")
            if closing < 0:
                raise ValueError
            fields = record[closing + 2:].split()
            if not fields:
                raise ValueError
            state = fields[0]
            if state in (b"Z", b"X", b"x"):
                return True
            if state not in (b"R", b"S", b"D", b"T", b"t", b"W", b"K", b"P", b"I"):
                raise ValueError
            return False
        except (OSError, ValueError, IndexError):
            raise SanitizerProcessExecutionError(BLOCK_MESSAGE) from None
    if sys.platform == "darwin":
        try:
            completed = subprocess.run(
                ("/bin/ps", "-o", "stat=", "-p", str(process.pid)),
                stdin=subprocess.DEVNULL,
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL,
                close_fds=True,
                cwd="/",
                env={"PATH": "/usr/bin:/bin", "LANG": "C"},
                timeout=0.25,
                check=True,
            )
            states = [
                line.strip() for line in completed.stdout.decode("ascii").splitlines()
                if line.strip()
            ]
            if len(states) != 1 or not states[0][0].isalpha():
                raise ValueError
            return states[0][0].upper() == "Z"
        except (OSError, ValueError, UnicodeDecodeError, subprocess.SubprocessError):
            raise SanitizerProcessExecutionError(BLOCK_MESSAGE) from None
    raise SanitizerProcessExecutionError(BLOCK_MESSAGE)


def _darwin_group_has_only_zombies(process_group_id: int) -> bool:
    """Confirm that a Darwin EPERM group has no executable descendants.

    macOS can return EPERM for a process group containing only an unreaped
    zombie. Never treat EPERM alone as successful cleanup: an unsignalable
    live descendant must remain a blocking failure.
    """
    try:
        completed = subprocess.run(
            ("/bin/ps", "-A", "-o", "pid=,pgid=,stat="),
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            close_fds=True,
            cwd="/",
            env={"PATH": "/usr/bin:/bin", "LANG": "C"},
            timeout=0.5,
            check=True,
        )
        for line in completed.stdout.decode("ascii").splitlines():
            fields = line.split()
            if (len(fields) != 3 or not fields[0].isdecimal()
                    or not fields[1].isdecimal() or not fields[2][0].isalpha()):
                return False
            if int(fields[1]) == process_group_id and fields[2][0].upper() != "Z":
                return False
        return True
    except (OSError, ValueError, UnicodeDecodeError, subprocess.SubprocessError):
        return False


def _stop_process_group(process):
    """Kill the whole isolated process group, including surviving descendants."""
    try:
        os.killpg(process.pid, signal.SIGKILL)
    except ProcessLookupError:
        if process.poll() is None:
            try:
                process.kill()
            except ProcessLookupError:
                pass
            except OSError:
                raise SanitizerProcessExecutionError(BLOCK_MESSAGE) from None
    except OSError as error:
        if error.errno == errno.EPERM and sys.platform == "darwin":
            try:
                if (_process_has_exited_without_reaping(process)
                        and _darwin_group_has_only_zombies(process.pid)):
                    return
            except SanitizerProcessExecutionError:
                pass
        try:
            process.kill()
        except (ProcessLookupError, OSError):
            pass
        raise SanitizerProcessExecutionError(BLOCK_MESSAGE) from None


def _reap_process(process):
    try:
        process.wait(timeout=REAP_TIMEOUT_SECONDS)
        return
    except subprocess.TimeoutExpired:
        pass
    except (OSError, subprocess.SubprocessError):
        raise SanitizerProcessExecutionError(BLOCK_MESSAGE) from None
    try:
        process.kill()
    except ProcessLookupError:
        pass
    except OSError:
        raise SanitizerProcessExecutionError(BLOCK_MESSAGE) from None
    try:
        process.wait(timeout=REAP_TIMEOUT_SECONDS)
    except (OSError, subprocess.SubprocessError):
        raise SanitizerProcessExecutionError(BLOCK_MESSAGE) from None


def _close_pipe(pipe):
    if pipe is not None and not pipe.closed:
        try:
            pipe.close()
        except OSError:
            pass


def run_limited_converter(
    command: tuple[str, ...],
    input_bytes: bytes,
    *,
    timeout_seconds: int,
    max_output_bytes: int,
    environment: dict[str, str],
) -> subprocess.CompletedProcess:
    """Run a trusted converter with hard input/output/time and memory bounds.

    Linux starts the converter through a fixed launcher that imposes RLIMIT_AS
    before exec. Both supported platforms poll aggregate process-group RSS and
    terminate the complete group if its 1-GiB budget is exceeded or cannot be
    measured. The caller supplies a fixed executable and sanitized environment;
    document data is provided only on stdin. stdout is capped while reading.
    """
    if (
        os.name != "posix"
        or type(command) is not tuple
        or not command
        or any(type(arg) is not str or not arg or "\x00" in arg for arg in command)
        or type(input_bytes) is not bytes
        or not 0 < len(input_bytes) <= MAX_INPUT_BYTES
        or type(timeout_seconds) is not int
        or not 1 <= timeout_seconds <= MAX_WALL_SECONDS
        or type(max_output_bytes) is not int
        or not 1 <= max_output_bytes <= MAX_OUTPUT_BYTES
        or type(environment) is not dict
        or any(
            type(key) is not str or not key or "=" in key or "\x00" in key
            or type(value) is not str or "\x00" in value
            for key, value in environment.items()
        )
    ):
        raise SanitizerProcessExecutionError(BLOCK_MESSAGE)

    process = None
    try:
        launch_command = _memory_limited_command(command)
        process = subprocess.Popen(
            launch_command,
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
            while events.get_map() or not _process_has_exited_without_reaping(process):
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise SanitizerProcessTimedOut(TIMEOUT_MESSAGE)
                if events.get_map():
                    ready = events.select(timeout=min(remaining, MEMORY_POLL_INTERVAL_SECONDS))
                else:
                    time.sleep(min(remaining, MEMORY_POLL_INTERVAL_SECONDS))
                    ready = []
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise SanitizerProcessTimedOut(TIMEOUT_MESSAGE)
                allow_empty = _process_has_exited_without_reaping(process)
                try:
                    resident_bytes = _process_group_memory_bytes(
                        process.pid,
                        allow_empty=allow_empty,
                        timeout_seconds=remaining,
                    )
                except SanitizerProcessMemoryLimitError:
                    if time.monotonic() >= deadline:
                        raise SanitizerProcessTimedOut(TIMEOUT_MESSAGE) from None
                    # The child may exit between the non-reaping wait check and
                    # the process-table snapshot. Retry only after confirming
                    # that exit; any surviving descendants remain in the group.
                    if (
                        not allow_empty
                        and _process_has_exited_without_reaping(process)
                    ):
                        remaining = deadline - time.monotonic()
                        if remaining <= 0:
                            raise SanitizerProcessTimedOut(TIMEOUT_MESSAGE) from None
                        try:
                            resident_bytes = _process_group_memory_bytes(
                                process.pid, allow_empty=True, timeout_seconds=remaining,
                            )
                        except SanitizerProcessMemoryLimitError:
                            if time.monotonic() >= deadline:
                                raise SanitizerProcessTimedOut(TIMEOUT_MESSAGE) from None
                            raise
                    else:
                        raise
                if resident_bytes > MAX_SANITIZER_MEMORY_BYTES:
                    raise SanitizerProcessMemoryLimitError(MEMORY_LIMIT_MESSAGE)
                for key, _ in ready:
                    if key.fileobj is process.stdout:
                        remaining_capacity = max_output_bytes - len(output)
                        chunk = os.read(
                            process.stdout.fileno(),
                            min(READ_CHUNK_BYTES, remaining_capacity + 1),
                        )
                        if not chunk:
                            events.unregister(process.stdout)
                            process.stdout.close()
                        elif len(output) + len(chunk) > max_output_bytes:
                            raise SanitizerProcessOutputLimitExceeded(OUTPUT_LIMIT_MESSAGE)
                        else:
                            output.extend(chunk)
                    else:
                        try:
                            written = os.write(
                                process.stdin.fileno(),
                                memoryview(input_bytes)[position:position + READ_CHUNK_BYTES],
                            )
                            position += written
                        except BlockingIOError:
                            continue
                        except BrokenPipeError:
                            position = len(input_bytes)
                        if position >= len(input_bytes):
                            events.unregister(process.stdin)
                            process.stdin.close()

        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise SanitizerProcessTimedOut(TIMEOUT_MESSAGE)
        if not _process_has_exited_without_reaping(process):
            raise SanitizerProcessTimedOut(TIMEOUT_MESSAGE)
        # Stop descendants before reaping the group leader, so its PID cannot
        # be reused for an unrelated process group during cleanup.
        _stop_process_group(process)
        try:
            return_code = process.wait(timeout=REAP_TIMEOUT_SECONDS)
        except subprocess.TimeoutExpired:
            raise SanitizerProcessTimedOut(TIMEOUT_MESSAGE) from None
        _close_pipe(process.stdin)
        _close_pipe(process.stdout)
        process = None
        if (sys.platform == "linux" and
                return_code == MEMORY_LIMIT_SETUP_FAILED_EXIT_CODE):
            raise SanitizerProcessMemoryLimitError(MEMORY_LIMIT_MESSAGE)
        return subprocess.CompletedProcess(command, return_code, bytes(output), None)
    except SanitizerProcessExecutionError:
        raise
    except (OSError, ValueError, RuntimeError, subprocess.SubprocessError):
        raise SanitizerProcessExecutionError(BLOCK_MESSAGE) from None
    finally:
        if process is not None:
            cleanup_error = None
            try:
                _stop_process_group(process)
            except SanitizerProcessExecutionError as error:
                cleanup_error = error
            try:
                _reap_process(process)
            except SanitizerProcessExecutionError as error:
                cleanup_error = cleanup_error or error
            _close_pipe(process.stdin)
            _close_pipe(process.stdout)
            if cleanup_error is not None:
                raise cleanup_error
