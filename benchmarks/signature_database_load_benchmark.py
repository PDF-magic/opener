#!/usr/bin/env python3
"""Opt-in, read-only libclamav signature loading benchmark; never a scan verdict.

Each sample runs in a fresh bounded process. The child measures cl_load and
cl_engine_compile directly, not a clamscan invocation or a PDF opening.
"""

import argparse
import ctypes
import json
import math
import os
from pathlib import Path
import re
import stat
import statistics
import subprocess
import sys
import time

TRUSTED_LIBRARIES = (
    "/opt/homebrew/opt/clamav/lib/libclamav.dylib",
    "/opt/homebrew/lib/libclamav.dylib",
    "/usr/local/opt/clamav/lib/libclamav.dylib",
    "/usr/local/lib/libclamav.dylib",
    "/usr/local/clamav/lib/libclamav.dylib",
)
DEFAULT_DATABASE = Path.home() / "Library/Application Support/Studio/allow-and-open/signatures"
MIN_SAMPLES = 3
MAX_SAMPLES = 7
TIMEOUT_SECONDS = 180
ERROR = "Signature load benchmark was unavailable or incomplete; no results were recorded."
VERSION_PATTERN = re.compile(r"^[A-Za-z0-9.+_-]{1,40}$")
MEASURED_KEYS = frozenset(("loadMs", "compileMs", "readyMs", "signatureCount", "engineVersion"))


class BenchmarkError(RuntimeError):
    pass


def validate_database(database):
    """Require real nonempty main and daily database files without following symlinks."""
    if not isinstance(database, Path):
        raise BenchmarkError(ERROR)
    try:
        root = os.lstat(database)
        if not stat.S_ISDIR(root.st_mode):
            raise BenchmarkError(ERROR)
        for stem in ("main", "daily"):
            count = 0
            for suffix in (".cvd", ".cld"):
                try:
                    entry = os.lstat(database / (stem + suffix))
                except FileNotFoundError:
                    continue
                if not stat.S_ISREG(entry.st_mode) or entry.st_size <= 0:
                    raise BenchmarkError(ERROR)
                count += 1
            if count != 1:
                raise BenchmarkError(ERROR)
    except OSError as exc:
        raise BenchmarkError(ERROR) from exc


def validate_inputs(library, database, samples):
    if (type(library) is not str or library not in TRUSTED_LIBRARIES or
            not Path(library).is_file() or not os.access(library, os.R_OK)):
        raise BenchmarkError(ERROR)
    validate_database(database)
    if type(samples) is not int or not MIN_SAMPLES <= samples <= MAX_SAMPLES:
        raise BenchmarkError(ERROR)


def native_sample(library, database, *, loader=ctypes.CDLL, clock=time.perf_counter):
    """Measure native cl_load and engine compilation with no file scanning."""
    engine = None
    try:
        api = loader(library)
        api.cl_init.argtypes = [ctypes.c_uint]
        api.cl_init.restype = ctypes.c_int
        api.cl_engine_new.argtypes = []
        api.cl_engine_new.restype = ctypes.c_void_p
        api.cl_load.argtypes = [
            ctypes.c_char_p, ctypes.c_void_p, ctypes.POINTER(ctypes.c_uint), ctypes.c_uint,
        ]
        api.cl_load.restype = ctypes.c_int
        api.cl_engine_compile.argtypes = [ctypes.c_void_p]
        api.cl_engine_compile.restype = ctypes.c_int
        api.cl_engine_free.argtypes = [ctypes.c_void_p]
        api.cl_engine_free.restype = ctypes.c_int
        api.cl_retver.argtypes = []
        api.cl_retver.restype = ctypes.c_char_p
        if api.cl_init(0) != 0:
            raise BenchmarkError(ERROR)
        engine = api.cl_engine_new()
        if not engine:
            raise BenchmarkError(ERROR)
        count = ctypes.c_uint(0)
        started = clock()
        load_status = api.cl_load(os.fsencode(database), engine, ctypes.byref(count), 0)
        loaded = clock()
        if load_status != 0 or count.value == 0:
            raise BenchmarkError(ERROR)
        compile_status = api.cl_engine_compile(engine)
        compiled = clock()
        if compile_status != 0:
            raise BenchmarkError(ERROR)
        version = api.cl_retver()
        version = version.decode("ascii") if isinstance(version, bytes) else ""
        result = {
            "loadMs": (loaded - started) * 1000,
            "compileMs": (compiled - loaded) * 1000,
            "readyMs": (compiled - started) * 1000,
            "signatureCount": count.value,
            "engineVersion": version,
        }
        return validate_sample(result)
    except (OSError, AttributeError, TypeError, ValueError, UnicodeError) as exc:
        raise BenchmarkError(ERROR) from exc
    finally:
        if engine:
            api.cl_engine_free(engine)


def validate_sample(result):
    if not isinstance(result, dict) or set(result) != MEASURED_KEYS:
        raise BenchmarkError(ERROR)
    if (type(result["signatureCount"]) is not int or result["signatureCount"] <= 0 or
            type(result["engineVersion"]) is not str or
            not VERSION_PATTERN.fullmatch(result["engineVersion"])):
        raise BenchmarkError(ERROR)
    for key in ("loadMs", "compileMs", "readyMs"):
        value = result[key]
        if (type(value) not in (float, int) or not math.isfinite(value) or
                value < 0 or value > TIMEOUT_SECONDS * 1000):
            raise BenchmarkError(ERROR)
    if result["loadMs"] <= 0 or result["readyMs"] <= 0:
        raise BenchmarkError(ERROR)
    if result["readyMs"] < result["loadMs"] or result["readyMs"] < result["compileMs"]:
        raise BenchmarkError(ERROR)
    return result


def bounded_sample(library, database, *, runner=subprocess.run):
    command = [
        sys.executable, "-I", str(Path(__file__).resolve()), "--child",
        "--library", library, "--database", str(database),
    ]
    try:
        completed = runner(command, capture_output=True, text=True,
                           timeout=TIMEOUT_SECONDS, check=False)
    except (OSError, subprocess.SubprocessError) as exc:
        raise BenchmarkError(ERROR) from exc
    if (completed.returncode != 0 or not isinstance(completed.stdout, str) or
            len(completed.stdout) > 1024 or not isinstance(completed.stderr, str) or
            completed.stderr.strip()):
        raise BenchmarkError(ERROR)
    try:
        return validate_sample(json.loads(completed.stdout))
    except (ValueError, TypeError) as exc:
        raise BenchmarkError(ERROR) from exc


def percentile90(samples):
    ordered = sorted(samples)
    return ordered[math.ceil(len(ordered) * 0.9) - 1]


def measure(library, database=DEFAULT_DATABASE, samples=5, *, runner=subprocess.run):
    """Discard one warmup; report only aggregates from successful native loads."""
    validate_inputs(library, database, samples)
    bounded_sample(library, database, runner=runner)
    results = [bounded_sample(library, database, runner=runner) for _ in range(samples)]
    baseline = (results[0]["signatureCount"], results[0]["engineVersion"])
    if any((item["signatureCount"], item["engineVersion"]) != baseline for item in results):
        raise BenchmarkError(ERROR)
    loads = [item["loadMs"] for item in results]
    compiles = [item["compileMs"] for item in results]
    ready = [item["readyMs"] for item in results]
    return {
        "schemaVersion": 1,
        "scope": "libclamavSignatureDatabaseLoad",
        "scannerVerdict": False,
        "sampleCount": samples,
        "signatureCount": baseline[0],
        "engineVersion": baseline[1],
        "medianLoadMs": round(statistics.median(loads), 3),
        "p90LoadMs": round(percentile90(loads), 3),
        "medianCompileMs": round(statistics.median(compiles), 3),
        "medianReadyMs": round(statistics.median(ready), 3),
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--library", required=True,
                        help="absolute path to an existing trusted libclamav shared library")
    parser.add_argument("--database", type=Path, default=DEFAULT_DATABASE,
                        help="installed ClamAV signatures directory")
    parser.add_argument("--samples", type=int, default=5)
    parser.add_argument("--child", action="store_true", help=argparse.SUPPRESS)
    args = parser.parse_args(argv)
    try:
        validate_inputs(args.library, args.database, args.samples)
        report = (native_sample(args.library, args.database) if args.child else
                  measure(args.library, args.database, args.samples))
    except BenchmarkError:
        parser.exit(1, ERROR + "\n")
    print(json.dumps(report, sort_keys=True, allow_nan=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
