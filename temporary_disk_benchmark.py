#!/usr/bin/env python3
"""Measure isolated Maximum PDF staging disk usage, not scanner or sanitizer usage.

The input is a bounded, generated PDF; no user's files, signature databases,
preferences, scanner, sanitization or PDF-opening APIs are accessed. Observed
peaks are sampled after completed stage operations, not continuous I/O peaks.
"""

import argparse
import json
import statistics
import tempfile
from pathlib import Path
from unittest.mock import patch

import maximum_temporary_output as staging
from pdf_parser_memory_benchmark import synthetic_pdf

MAX_RUNS = 5
MAX_COPIES = 4
STREAM_KIB = (64, 1024)
ERROR = "Temporary disk benchmark incomplete; no measurements recorded."


def _validate(stream_kib, copies, runs):
    if type(stream_kib) is not int or stream_kib not in STREAM_KIB:
        raise ValueError("Select a fixed synthetic PDF size (64 or 1024 KiB).")
    if type(copies) is not int or not 1 <= copies <= MAX_COPIES:
        raise ValueError("Select one to four concurrent staged copies.")
    if type(runs) is not int or not 1 <= runs <= MAX_RUNS:
        raise ValueError("Select one to five completed samples.")


def _usage(leases):
    """Stat only the known owned paths, not other filesystem entries."""
    logical = 0
    allocated = 0
    for lease in leases:
        lease.verify()
        file_info = lease.path.stat(follow_symlinks=False)
        dir_info = lease.path.parent.stat(follow_symlinks=False)
        lease.verify()
        if (file_info.st_nlink != 1 or
                not hasattr(file_info, "st_blocks") or
                not hasattr(dir_info, "st_blocks") or
                file_info.st_blocks < 0 or dir_info.st_blocks < 0):
            raise RuntimeError(ERROR)
        logical += file_info.st_size
        # st_blocks counts 512-byte blocks; include the owned staging
        # directory, but exclude the independent TemporaryDirectory/root.
        allocated += 512 * (file_info.st_blocks + dir_info.st_blocks)
    return logical, allocated


def _sample(pdf, copies):
    """Stage/verify every output and verify release in a fresh private root."""
    try:
        with tempfile.TemporaryDirectory(prefix="pdfmagic-disk-benchmark-") as parent:
            root = Path(parent) / "owned-copies"
            root.mkdir(mode=0o700)
            with patch.object(staging, "_PRIVATE_ROOT", root):
                leases = []
                logical_peak = 0
                allocated_peak = 0
                try:
                    for count in range(1, copies + 1):
                        lease = staging.stage_maximum_temporary_pdf(pdf)
                        leases.append(lease)
                        logical, allocated = _usage(leases)
                        if logical != count * len(pdf):
                            raise RuntimeError(ERROR)
                        logical_peak = max(logical_peak, logical)
                        allocated_peak = max(allocated_peak, allocated)
                finally:
                    # Always release even on a failed stage, stat or validation.
                    release_failed = False
                    for lease in reversed(leases):
                        try:
                            lease.release()
                        except Exception:
                            release_failed = True
                    if release_failed:
                        raise RuntimeError(ERROR)
                if any(root.iterdir()):
                    raise RuntimeError(ERROR)
                return logical_peak, allocated_peak, 0
    except Exception:
        # Never expose private staging paths or partial measurements.
        raise RuntimeError(ERROR) from None


def benchmark(stream_kib=64, copies=2, runs=3):
    _validate(stream_kib, copies, runs)
    pdf = synthetic_pdf(1, stream_kib * 1024)
    if (not pdf.startswith(b"%PDF-") or not pdf.endswith(b"%%EOF\n") or
            len(pdf) > staging.MAX_TEMP_PDF_BYTES):
        raise RuntimeError(ERROR)
    # One discarded warmup. Every run stages and releases in a new directory.
    try:
        _sample(pdf, copies)
        results = [_sample(pdf, copies) for _ in range(runs)]
        if any(logical != copies * len(pdf) or after != 0
               for logical, _, after in results):
            raise RuntimeError(ERROR)
        return {
            "schemaVersion": 1,
            "scope": "maximumTemporaryPdfStagingOnly",
            "fixture": "syntheticInertPdf",
            "inputBytes": len(pdf),
            "copies": copies,
            "sampleCount": runs,
            "discardedWarmupRuns": 1,
            "medianObservedPeakLogicalBytes": int(statistics.median(r[0] for r in results)),
            "maxObservedPeakAllocatedBytes": max(r[1] for r in results),
            "maxPostReleaseAllocatedBytes": max(r[2] for r in results),
            "authorizesOpen": False,
        }
    except Exception:
        raise RuntimeError(ERROR) from None


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--stream-kib", type=int, default=64)
    parser.add_argument("--copies", type=int, default=2)
    parser.add_argument("--runs", type=int, default=3)
    args = parser.parse_args(argv)
    try:
        report = benchmark(args.stream_kib, args.copies, args.runs)
    except (RuntimeError, ValueError) as error:
        parser.exit(1, str(error) + "\n")
    print(json.dumps(report, sort_keys=True, allow_nan=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
