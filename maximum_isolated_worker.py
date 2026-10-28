"""Internal worker for the planned Maximum isolated-analysis stage.

Only a fixed set of trusted passive inspectors can run here. This module
receives PDF bytes on stdin and returns bounded numeric evidence on stdout.
It is not a command shell, user-facing entrypoint or PDF clean verdict.
"""
import json
import os
import sys


def _apply_limits():
    # Limits are applied before importing project PDF parsing modules.
    # When the OS cannot enforce the isolation contract, fail closed.
    import resource

    from maximum_isolated_analysis import (
        WORKER_CPU_SECONDS, WORKER_MEMORY_MIB,
    )
    ceilings = (
        (resource.RLIMIT_CORE, 0),
        (resource.RLIMIT_FSIZE, 0),
        (resource.RLIMIT_CPU, WORKER_CPU_SECONDS),
        # On macOS, a fresh interpreter maps a large shared dyld cache into
        # virtual address space. RLIMIT_AS can therefore reject innocent
        # parser imports despite tiny resident memory. Bound the data segment
        # there; Linux enforces the whole address space instead.
        (resource.RLIMIT_DATA if sys.platform == "darwin" else resource.RLIMIT_AS,
         WORKER_MEMORY_MIB * 1024 * 1024),
    )
    for name, ceiling in ceilings:
        _, hard = resource.getrlimit(name)
        effective = ceiling if hard == resource.RLIM_INFINITY else min(ceiling, hard)
        resource.setrlimit(name, (effective, effective))


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
    raise SystemExit(exit_code)
