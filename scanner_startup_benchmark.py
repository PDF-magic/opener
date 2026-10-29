#!/usr/bin/env python3
"""Opt-in measurement of clamscan invocation overhead; never a scan verdict.

Runs only an existing, trusted local clamscan executable on synthetic files.
No clamd service, network connection, persisted settings, cache, or opening API.
"""

import argparse
import json
import math
import os
import re
from pathlib import Path
import statistics
import subprocess
import tempfile
import time

TRUSTED_SCANNERS = (
    "/opt/homebrew/bin/clamscan",
    "/usr/local/bin/clamscan",
    "/usr/local/clamav/bin/clamscan",
)
DEFAULT_DATABASE = Path.home() / "Library/Application Support/Studio/allow-and-open/signatures"
MIN_FILES = 5
MAX_FILES = 20
MIN_CYCLES = 3
MAX_CYCLES = 5
TIMEOUT_SECONDS = 180
ERROR = "Benchmark scan was unavailable or incomplete; no results were recorded."
DIAGNOSTIC_LINE = re.compile(
    r"^(?:(?:Lib)?ClamAV\s+)?(?:warning|warn|error|failed|skipped)\s*:",
    re.IGNORECASE,
)


def validate_inputs(scanner, database, file_count, cycles):
    """Restrict opt-in execution to already supported ClamAV installations."""
    if (type(scanner) is not str or scanner not in TRUSTED_SCANNERS or
            not Path(scanner).is_file() or not os.access(scanner, os.X_OK)):
        raise ValueError("Choose an installed, trusted clamscan executable.")
    if not isinstance(database, Path) or not database.is_dir():
        raise ValueError("The installed ClamAV signature directory is unavailable.")
    if type(file_count) is not int or not MIN_FILES <= file_count <= MAX_FILES:
        raise ValueError("The benchmark needs 5 to 20 synthetic files.")
    if type(cycles) is not int or not MIN_CYCLES <= cycles <= MAX_CYCLES:
        raise ValueError("The benchmark needs 3 to 5 paired cycles.")


def command(scanner, database, operand):
    # A standalone PDF uses the same ClamAV policy flags as the installed gate.
    # The batch operation is diagnostic only and cannot replace that gate.
    return [
        scanner, "--database=" + str(database), "--recursive",
        "--follow-file-symlinks=2", "--follow-dir-symlinks=2",
        "--alert-exceeds-max=yes", "--alert-encrypted=yes",
        "--max-filesize=0", "--max-scansize=0",
        "--max-scantime=0", "--no-summary", "--", str(operand),
    ]


def synthetic_pdf(index):
    # Never use selected, downloaded or user-supplied files as benchmark inputs.
    return (b"%PDF-1.4\n1 0 obj\n<< /Type /Catalog >>\nendobj\n"
            + ("%% synthetic fixture %02d\n" % index).encode("ascii")
            + b"%%EOF\n")


def timed_scan(scanner, database, operand, expected_count, *, runner=subprocess.run,
               clock=time.perf_counter):
    started = clock()
    try:
        completed = runner(
            command(scanner, database, operand), capture_output=True,
            text=True, timeout=TIMEOUT_SECONDS, check=False,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        raise RuntimeError(ERROR) from exc
    duration = clock() - started
    # Never accept partial reads, a scanner warning, or a non-clean exit as
    # timing data. Do not include raw stdout/stderr, filenames or paths in output.
    lines = completed.stdout.splitlines() if isinstance(completed.stdout, str) else ()
    if (completed.returncode != 0 or not isinstance(completed.stderr, str) or
            completed.stderr.strip() or len(lines) != expected_count or
            any(not line.endswith(": OK") or DIAGNOSTIC_LINE.match(line.lstrip())
                for line in lines) or
            not math.isfinite(duration) or duration <= 0):
        raise RuntimeError(ERROR)
    return duration


def measure(scanner, database, file_count=5, cycles=3, *, runner=subprocess.run,
            clock=time.perf_counter):
    """Compare repeated clamscan starts with one invocation per fixture set.

    This is *not* clamd performance evidence. A separate daemon benchmark and
    security review remain prerequisites to proposing a production switch.
    """
    validate_inputs(scanner, database, file_count, cycles)
    with tempfile.TemporaryDirectory(prefix="clamscan-startup-") as folder:
        root = Path(folder)
        for i in range(file_count):
            (root / ("fixture-%02d.pdf" % i)).write_bytes(synthetic_pdf(i))
        files = sorted(root.glob("fixture-*.pdf"))
        if len(files) != file_count:
            raise RuntimeError(ERROR)
        # Explicit warmup: neither a cold filesystem cache nor scan policy
        # setup should be presented as a persistent-daemon speed comparison.
        timed_scan(scanner, database, files[0], 1, runner=runner, clock=clock)
        singles = []
        batches = []
        for cycle in range(cycles):
            # Alternate phase order to reduce warm-cache order bias.
            if cycle % 2:
                batches.append(timed_scan(scanner, database, root, file_count,
                                          runner=runner, clock=clock))
            singles.append(sum(timed_scan(scanner, database, path, 1,
                                          runner=runner, clock=clock) for path in files))
            if not cycle % 2:
                batches.append(timed_scan(scanner, database, root, file_count,
                                          runner=runner, clock=clock))
        # No result is published until *all* runs have completed successfully.
        one_shot = statistics.median(singles)
        batched = statistics.median(batches)
        return {
            "schemaVersion": 1,
            "scope": "syntheticClamscanStartupExperiment",
            "evidenceForClamdSwitch": False,
            "fixtureCount": file_count,
            "pairedCycles": cycles,
            "oneShotInvocationsPerCycle": file_count,
            "medianRepeatedOneShotMs": round(one_shot * 1000, 3),
            "medianOneProcessBatchMs": round(batched * 1000, 3),
            "medianExcessOneShotMs": round((one_shot - batched) * 1000, 3),
        }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--scanner", required=True,
                        help="absolute path to an installed supported clamscan")
    parser.add_argument("--database", type=Path, default=DEFAULT_DATABASE,
                        help="installed signature directory (default: existing opener path)")
    parser.add_argument("--files", type=int, default=5)
    parser.add_argument("--cycles", type=int, default=3)
    args = parser.parse_args(argv)
    try:
        report = measure(args.scanner, args.database, args.files, args.cycles)
    except (ValueError, RuntimeError) as exc:
        parser.exit(1, str(exc) + "\n")
    print(json.dumps(report, sort_keys=True, allow_nan=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
