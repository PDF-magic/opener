#!/usr/bin/env python3
"""Opt-in per-process CPU measurement of real ClamAV scans of an inert PDF.

This is diagnostic evidence only, never a scan verdict or opening permission.
"""

import argparse
from dataclasses import dataclass
import json
import math
import os
from pathlib import Path
import signal
import statistics
import subprocess
import tempfile
import time

from reference_pdf_collection import REFERENCE_PDFS
from scanner_startup_benchmark import (DEFAULT_DATABASE, DIAGNOSTIC_LINE,
                                       TIMEOUT_SECONDS, TRUSTED_SCANNERS, command)

MIN_SAMPLES = 3
MAX_SAMPLES = 7
MAX_OUTPUT_BYTES = 65536
ERROR = "CPU benchmark failed or was incomplete; no measurements recorded."


@dataclass(frozen=True)
class ProcessSample:
    user_seconds: float
    system_seconds: float
    wall_seconds: float
    exit_code: int
    stdout: str
    stderr: str


def run_clamscan(args):
    """Reap one child with wait4 so CPU time belongs to that scanner alone."""
    if not hasattr(os, "wait4"):
        raise RuntimeError(ERROR)
    with tempfile.TemporaryFile() as output, tempfile.TemporaryFile() as errors:
        started = time.monotonic()
        process = subprocess.Popen(args, stdin=subprocess.DEVNULL, stdout=output,
                                   stderr=errors, close_fds=True)
        try:
            while True:
                pid, status, usage = os.wait4(process.pid, os.WNOHANG)
                if pid == process.pid:
                    break
                if time.monotonic() - started >= TIMEOUT_SECONDS:
                    raise RuntimeError(ERROR)
                time.sleep(0.02)
        except BaseException:
            try:
                os.kill(process.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            try:
                os.waitpid(process.pid, 0)
            except ChildProcessError:
                pass
            process.returncode = -signal.SIGKILL
            raise
        process.returncode = os.waitstatus_to_exitcode(status)
        elapsed = time.monotonic() - started
        output.seek(0)
        errors.seek(0)
        raw_stdout = output.read(MAX_OUTPUT_BYTES + 1)
        raw_stderr = errors.read(MAX_OUTPUT_BYTES + 1)
        if len(raw_stdout) > MAX_OUTPUT_BYTES or len(raw_stderr) > MAX_OUTPUT_BYTES:
            raise RuntimeError(ERROR)
        return ProcessSample(usage.ru_utime, usage.ru_stime, elapsed,
                             process.returncode, raw_stdout.decode("utf-8", "replace"),
                             raw_stderr.decode("utf-8", "replace"))


def validate_sample(sample, path):
    if type(sample) is not ProcessSample:
        raise RuntimeError(ERROR)
    values = (sample.user_seconds, sample.system_seconds, sample.wall_seconds)
    if (any(type(value) not in (int, float) or not math.isfinite(value) or value < 0
            for value in values) or sample.wall_seconds <= 0 or
            sample.user_seconds + sample.system_seconds <= 0 or
            sample.exit_code != 0 or type(sample.stdout) is not str or
            type(sample.stderr) is not str or sample.stderr.strip()):
        raise RuntimeError(ERROR)
    lines = sample.stdout.strip().splitlines()
    if (len(lines) != 1 or lines[0] != f"{path}: OK" or
            DIAGNOSTIC_LINE.match(lines[0].lstrip())):
        raise RuntimeError(ERROR)
    return sample


def benchmark(scanner, database=DEFAULT_DATABASE, samples=5, *, runner=run_clamscan):
    """Discard one warmup and aggregate only fully completed real child runs."""
    if (type(scanner) is not str or scanner not in TRUSTED_SCANNERS or
            not Path(scanner).is_file() or not os.access(scanner, os.X_OK) or
            not isinstance(database, Path) or not database.is_dir() or
            type(samples) is not int or not MIN_SAMPLES <= samples <= MAX_SAMPLES):
        raise ValueError("Requires a trusted clamscan, signature directory, and 3–7 samples.")
    document = REFERENCE_PDFS[0].content
    if (type(document) is not bytes or not document.startswith(b"%PDF-1.4\n") or
            not document.endswith(b"%%EOF\n") or len(document) >= 4096):
        raise RuntimeError(ERROR)
    with tempfile.TemporaryDirectory(prefix="pdf-cpu-benchmark-") as directory:
        pdf = Path(directory) / "inert-fixture.pdf"
        pdf.write_bytes(document)
        records = []
        for index in range(samples + 1):
            try:
                record = validate_sample(runner(command(scanner, database, pdf)), pdf)
            except Exception:
                # Never print scanner stderr, user paths, or partial data.
                raise RuntimeError(ERROR) from None
            if index:
                records.append(record)
    cpu_ms = sorted((r.user_seconds + r.system_seconds) * 1000 for r in records)
    percentages = [100 * (r.user_seconds + r.system_seconds) / r.wall_seconds
                   for r in records]
    return {
        "schemaVersion": 1,
        "scope": "isolatedClamscanProcessCpuIncludingSignatureLoad",
        "fixture": "syntheticOnePageTextPdf",
        "fixtureBytes": len(document),
        "samples": samples,
        "discardedWarmups": 1,
        "authorizesOpen": False,
        "medianUserCpuMs": round(statistics.median(r.user_seconds for r in records) * 1000, 3),
        "medianSystemCpuMs": round(statistics.median(r.system_seconds for r in records) * 1000, 3),
        "medianTotalCpuMs": round(statistics.median(cpu_ms), 3),
        "p90TotalCpuMs": round(cpu_ms[math.ceil(0.9 * samples) - 1], 3),
        "medianWallMs": round(statistics.median(r.wall_seconds for r in records) * 1000, 3),
        "medianCpuPercent": round(statistics.median(percentages), 2),
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--scanner", required=True,
                        help="absolute path to an existing trusted clamscan binary")
    parser.add_argument("--database", type=Path, default=DEFAULT_DATABASE)
    parser.add_argument("--samples", type=int, default=5)
    args = parser.parse_args(argv)
    try:
        report = benchmark(args.scanner, args.database, args.samples)
    except (OSError, ValueError, RuntimeError, subprocess.SubprocessError):
        parser.exit(1, ERROR + "\n")
    print(json.dumps(report, sort_keys=True, allow_nan=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
