"""Internal worker for the planned Maximum isolated-analysis stage.

Only a fixed set of trusted passive inspectors can run here. This module
receives PDF bytes on stdin and returns bounded numeric evidence on stdout.
It is not a command shell, user-facing entrypoint or PDF clean verdict.
"""
import json
import os
import sys


def _apply_limits():
    # Fail closed on any missing OS resource limit. Apply CPU and no-file
    # limits before bringing in the memory guard and PDF parser modules.
    import resource
    from maximum_isolated_analysis import WORKER_CPU_SECONDS
    from maximum_memory_limits import impose_maximum_worker_memory_limit

    ceilings = (
        (resource.RLIMIT_CORE, 0),
        (resource.RLIMIT_FSIZE, 0),
        (resource.RLIMIT_CPU, WORKER_CPU_SECONDS),
    )
    for name, ceiling in ceilings:
        soft, hard = resource.getrlimit(name)
        effective = ceiling
        for existing in (soft, hard):
            if existing != resource.RLIM_INFINITY:
                effective = min(effective, existing)
        resource.setrlimit(name, (effective, effective))

    # The child, not the caller or the deployed scanner, receives the cap.
    impose_maximum_worker_memory_limit()

def main():
    if len(sys.argv) != 2:
        return 2
    # -I drops the script directory from sys.path. Restore only this
    # trusted repository directory, never the untrusted process cwd.
    sys.path.insert(0, os.path.dirname(os.path.realpath(__file__)))
    _apply_limits()

    from importlib import import_module
    from maximum_isolated_analysis import MAX_PDF_BYTES, _INSPECTORS

    inspection = sys.argv[1]
    if inspection not in _INSPECTORS:
        return 2
    contents = sys.stdin.buffer.read(MAX_PDF_BYTES + 1)
    if not 0 < len(contents) <= MAX_PDF_BYTES:
        return 2

    module_name, function_name, keys = _INSPECTORS[inspection]
    inspector = getattr(import_module(module_name), function_name)
    report = inspector(contents)
    if getattr(report, "permits_open", None) is not False:
        return 2
    metrics = {}
    for key in keys:
        number = getattr(report, key)
        if type(number) is not int or not 0 <= number <= 2**31 - 1:
            return 2
        metrics[key] = number
    payload = {
        "protocol": 1, "inspection": inspection, "workerPid": os.getpid(),
        "metrics": metrics, "permitsOpen": False,
    }
    sys.stdout.write(json.dumps(payload, separators=(",", ":")) + "\n")
    sys.stdout.flush()
    return 0


if __name__ == "__main__":
    try:
        exit_code = main()
    except BaseException:
        # Never reflect a parser traceback, PDF text, path or exception in
        # stdout/stderr; the parent always reports a fixed blocked outcome.
        exit_code = 2
    finally:
        # Keep the mandatory macOS memory watchdog armed during all untrusted
        # parsing, but disarm it before Python interpreter teardown. A late
        # SIGALRM after a complete result must not corrupt the worker exit.
        if sys.platform == "darwin":
            try:
                import signal
                signal.setitimer(signal.ITIMER_REAL, 0)
            except BaseException:
                exit_code = 2
    raise SystemExit(exit_code)
