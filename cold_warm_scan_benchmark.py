#!/usr/bin/env python3
"""Opt-in paired first-pass/repeat ClamAV scan timings of inert PDFs.

"Cold" means first benchmark scan of a new fixture path; "warm" means
immediate repeat on that same path. This never clears OS caches or keeps a
scanner engine alive and is not a claim about true cold-start disk latency.
"""

import argparse
import json
import math
import os
from pathlib import Path
import statistics
import subprocess
import tempfile
import time

from reference_pdf_collection import REFERENCE_PDFS
from scanner_startup_benchmark import (DEFAULT_DATABASE, TIMEOUT_SECONDS,
                                       TRUSTED_SCANNERS, command)

MIN_PAIRS = 3
MAX_PAIRS = 7
ERROR = "Cold/warm scan benchmark failed or was incomplete; no results recorded."


def validate_inputs(scanner, database, pairs):
    if (type(scanner) is not str or scanner not in TRUSTED_SCANNERS or
            not Path(scanner).is_file() or not os.access(scanner, os.X_OK) or
            not isinstance(database, Path) or not database.is_dir() or
            type(pairs) is not int or not MIN_PAIRS <= pairs <= MAX_PAIRS):
        raise ValueError(ERROR)


def timed_scan(scanner, database, pdf, *, runner=subprocess.run,
               clock=time.perf_counter):
    """Measure a fresh clamscan process, rejecting every non-clean outcome."""
    args = command(scanner, database, pdf)
    try:
        started = clock()
        result = runner(args, capture_output=True, text=True,
                        timeout=TIMEOUT_SECONDS, check=False)
        elapsed = clock() - started
    except (OSError, subprocess.SubprocessError, ValueError, OverflowError) as exc:
        raise RuntimeError(ERROR) from exc
    if (result.returncode != 0 or type(result.stdout) is not str or
            result.stdout.strip() != f"{pdf}: OK" or
            len(result.stdout) > 65536 or type(result.stderr) is not str or
            result.stderr.strip() or not math.isfinite(elapsed) or
            elapsed <= 0 or elapsed > TIMEOUT_SECONDS):
        raise RuntimeError(ERROR)
    return elapsed


def benchmark(scanner, database=DEFAULT_DATABASE, pairs=5, *,
              runner=subprocess.run, clock=time.perf_counter):
    """Discard a calibration pair; publish only complete, validated pairs."""
    validate_inputs(scanner, database, pairs)
    content = REFERENCE_PDFS[0].content
    if (type(content) is not bytes or not content.startswith(b"%PDF-1.4\n") or
            not content.endswith(b"%%EOF\n") or len(content) >= 4096):
        raise RuntimeError(ERROR)
    records = []
    try:
        with tempfile.TemporaryDirectory(prefix="pdf-cold-warm-") as folder:
            for index in range(pairs + 1):
                pdf = Path(folder) / f"inert-{index:02d}.pdf"
                pdf.write_bytes(content)
                cold = timed_scan(scanner, database, pdf, runner=runner, clock=clock)
                warm = timed_scan(scanner, database, pdf, runner=runner, clock=clock)
                if index:
                    records.append((cold, warm))
    except (OSError, subprocess.SubprocessError, RuntimeError, ValueError):
        # Neither partial results nor private scanner diagnostics may escape.
        raise RuntimeError(ERROR) from None
    cold_ms = [a * 1000 for a, _ in records]
    warm_ms = [b * 1000 for _, b in records]
    differences = [(b - a) * 1000 for a, b in records]
    return {
        "schemaVersion": 1,
        "scope": "freshClamscanProcessFirstVsRepeatSameSyntheticPdf",
        "coldDefinition": "firstScanOfUniqueFixturePathAfterCalibration",
        "warmDefinition": "immediateRepeatOfSameFixturePath",
        "clearsOsCaches": False,
        "persistsScannerEngine": False,
        "authorizesOpen": False,
        "fixture": "inertOnePageTextPdf",
        "pairs": pairs,
        "discardedCalibrationPairs": 1,
        "medianColdMs": round(statistics.median(cold_ms), 3),
        "medianWarmMs": round(statistics.median(warm_ms), 3),
        "p90ColdMs": round(sorted(cold_ms)[math.ceil(pairs * 0.9) - 1], 3),
        "p90WarmMs": round(sorted(warm_ms)[math.ceil(pairs * 0.9) - 1], 3),
        "medianWarmMinusColdMs": round(statistics.median(differences), 3),
        "medianColdToWarmRatio": round(statistics.median(
            a / b for a, b in records), 3),
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--scanner", required=True, help="existing trusted clamscan executable")
    parser.add_argument("--database", type=Path, default=DEFAULT_DATABASE)
    parser.add_argument("--pairs", type=int, default=5)
    args = parser.parse_args(argv)
    try:
        report = benchmark(args.scanner, args.database, args.pairs)
    except (OSError, ValueError, RuntimeError, subprocess.SubprocessError):
        parser.exit(1, ERROR + "\n")
    print(json.dumps(report, sort_keys=True, allow_nan=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
