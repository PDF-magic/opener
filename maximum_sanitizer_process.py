"""Hard wall-time and process-tree limits for the optional Maximum PDF converter.

This is a passive sanitization primitive. It never scans, saves, opens, or
authorizes a PDF; failure to complete within the deadline returns no output.
"""
import os
import selectors
import signal
import subprocess
import time

MAX_INPUT_BYTES = 16 * 1024 * 1024
MAX_OUTPUT_BYTES = 32 * 1024 * 1024
MAX_WALL_SECONDS = 45
REAP_TIMEOUT_SECONDS = 3
READ_CHUNK_BYTES = 65536
BLOCK_MESSAGE = "PDF sanitization exceeded execution limits; no copy was offered."
TIMEOUT_MESSAGE = "PDF sanitization exceeded its execution deadline; no copy was offered."
OUTPUT_LIMIT_MESSAGE = "PDF sanitization exceeded its output limit; no copy was offered."


class SanitizerProcessExecutionError(RuntimeError):
    """Fixed, path-free failure to supervise the sanitizer process."""


class SanitizerProcessTimedOut(SanitizerProcessExecutionError):
    """The converter or an inherited output-pipe descendant exceeded its deadline."""


class SanitizerProcessOutputLimitExceeded(SanitizerProcessExecutionError):
    """The converter produced more bytes than the output budget."""


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
    except OSError:
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
    """Run a trusted converter with a hard wall deadline and bounded output.

    The caller supplies a fixed executable and sanitized environment; document
    data is provided only on stdin. A dedicated POSIX session is always killed
    and reaped, even after apparent success, so descendants cannot outlive the
    converter or hold stdout open indefinitely. stdout is capped while reading.
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
                    raise SanitizerProcessTimedOut(TIMEOUT_MESSAGE)
                for key, _ in events.select(timeout=min(remaining, 0.25)):
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
        try:
            return_code = process.wait(timeout=remaining)
        except subprocess.TimeoutExpired:
            raise SanitizerProcessTimedOut(TIMEOUT_MESSAGE) from None
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
