"""Bounded stdout capture for a trusted, separately launched Maximum worker.

Capture at most output_limit + 1 bytes; an overproducing child and its
descendants are killed and reaped without exposing diagnostic or PDF data.
"""
import os
import selectors
import signal
import subprocess
import time

MAX_INPUT_BYTES = 16 * 1024 * 1024
MAX_OUTPUT_BYTES = 4096
BLOCK_MESSAGE = "Maximum analysis output limit was exceeded or output was unavailable; opening was stopped."
CHUNK = 65536

class MaximumOutputLimitError(RuntimeError):
    """Fixed, path-free failure."""


def _stop(process):
    if process.poll() is None:
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except OSError:
            pass
        try:
            process.kill()
        except OSError:
            pass
    try:
        process.wait(timeout=2)
    except (OSError, subprocess.TimeoutExpired):
        pass


def run_bounded_worker(command, *, input_bytes, output_limit=MAX_OUTPUT_BYTES,
                       timeout, cwd, env):
    """Stream concurrent stdin/stdout with a strict parent-side byte ceiling.

    The caller owns command allowlisting and validates the worker response;
    neither this transport nor a zero exit code authorizes PDF opening.
    """
    if (type(command) is not list or not command or
            any(type(item) is not str or not item or "\x00" in item for item in command) or
            type(input_bytes) is not bytes or len(input_bytes) > MAX_INPUT_BYTES or
            type(output_limit) is not int or not 0 < output_limit <= MAX_OUTPUT_BYTES or
            type(timeout) not in (int, float) or not 0 < timeout <= 600 or
            type(cwd) is not str or cwd != "/" or type(env) is not dict or
            any(type(k) is not str or type(v) is not str for k, v in env.items())):
        raise MaximumOutputLimitError(BLOCK_MESSAGE)
    process = None
    selector = selectors.DefaultSelector()
    output = bytearray()
    try:
        deadline = time.monotonic() + timeout
        process = subprocess.Popen(
            command, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL, close_fds=True,
            start_new_session=True, cwd=cwd, env=env,
        )
        if process.stdin is None or process.stdout is None:
            raise MaximumOutputLimitError(BLOCK_MESSAGE)
        os.set_blocking(process.stdout.fileno(), False)
        selector.register(process.stdout, selectors.EVENT_READ)
        position = 0
        if input_bytes:
            os.set_blocking(process.stdin.fileno(), False)
            selector.register(process.stdin, selectors.EVENT_WRITE)
        else:
            process.stdin.close()
        while selector.get_map():
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise MaximumOutputLimitError(BLOCK_MESSAGE)
            for key, event in selector.select(remaining):
                if key.fileobj is process.stdout and event & selectors.EVENT_READ:
                    # Never copy more than the first byte beyond the limit.
                    amount = min(CHUNK, output_limit - len(output) + 1)
                    part = os.read(process.stdout.fileno(), amount)
                    if not part:
                        selector.unregister(process.stdout)
                        process.stdout.close()
                    else:
                        output.extend(part)
                        if len(output) > output_limit:
                            raise MaximumOutputLimitError(BLOCK_MESSAGE)
                elif key.fileobj is process.stdin and event & selectors.EVENT_WRITE:
                    try:
                        written = os.write(
                            process.stdin.fileno(),
                            memoryview(input_bytes)[position:position + CHUNK],
                        )
                        if written <= 0:
                            raise MaximumOutputLimitError(BLOCK_MESSAGE)
                        position += written
                    except BrokenPipeError:
                        position = len(input_bytes)
                    if position >= len(input_bytes):
                        selector.unregister(process.stdin)
                        process.stdin.close()
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise MaximumOutputLimitError(BLOCK_MESSAGE)
        return subprocess.CompletedProcess(command, process.wait(timeout=remaining), bytes(output))
    except Exception:
        raise MaximumOutputLimitError(BLOCK_MESSAGE) from None
    finally:
        selector.close()
        if process is not None:
            if process.poll() is None:
                _stop(process)
            for stream in (process.stdin, process.stdout):
                if stream is not None and not stream.closed:
                    stream.close()
