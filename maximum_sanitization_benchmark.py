#!/usr/bin/env python3
"""Opt-in timing of a real, verified Maximum raster-sanitization attempt.

The optional Maximum profile is not deployed. This benchmark neither scans
nor opens PDFs, writes output, changes preferences, or grants clean verdicts.
On non-macOS hosts without the trusted converter it fails without results.
"""

import argparse
import json
import math
import statistics
import time

from maximum_sanitized_copy import (
    SanitizedCopyOffer,
    SanitizerAttempt,
    attempt_sanitized_pdf_copy,
)
from reference_pdf_collection import REFERENCE_PDFS

MIN_SAMPLES = 3
MAX_SAMPLES = 10
ERROR = "Maximum sanitization benchmark failed or incomplete; no measurements recorded."


def fixture():
    """A fixed, harmless single-page PDF containing actual vector text."""
    item = next(item for item in REFERENCE_PDFS if item.identifier == "clean-basic")
    source = item.content
    if (type(source) is not bytes or not 0 < len(source) < 4096 or
            not source.startswith(b"%PDF-1.4\n") or
            b"(Clean baseline) Tj" not in source or
            not source.endswith(b"%%EOF\n")):
        raise RuntimeError(ERROR)
    return source


def benchmark(samples=3, *, sanitizer=attempt_sanitized_pdf_copy,
              clock=time.perf_counter_ns):
    """Time complete conversions, including the supervised native subprocess.

    One real conversion is discarded as warmup. Failed conversions or invalid
    elapsed times abort the entire batch without releasing partial results.
    """
    if type(samples) is not int or not MIN_SAMPLES <= samples <= MAX_SAMPLES:
        raise ValueError("Choose 3 to 10 complete Maximum benchmark samples.")
    source = fixture()
    durations = []
    output_sizes = []
    for index in range(samples + 1):
        try:
            start = clock()
            attempt = sanitizer(source)
            elapsed = clock() - start
            if type(attempt) is not SanitizerAttempt or attempt.failure is not None:
                raise RuntimeError(ERROR)
            offer = attempt.offer
            if (type(offer) is not SanitizedCopyOffer or
                    offer.page_count != 1 or offer.permits_open is not False or
                    offer.needs_separate_scan is not True or
                    offer.rasterized is not True or
                    offer.ocr_restored is not False or
                    not offer.pdf_bytes.startswith(b"%PDF-") or
                    offer.pdf_bytes == source or
                    type(elapsed) not in (int, float) or
                    not math.isfinite(elapsed) or elapsed <= 0):
                raise RuntimeError(ERROR)
        except Exception:
            # Never publish failures, PDF bytes, private paths, or partial times.
            raise RuntimeError(ERROR) from None
        if index:
            durations.append(elapsed)
            output_sizes.append(len(offer.pdf_bytes))
    ordered = sorted(durations)
    return {
        "schemaVersion": 1,
        "scope": "maximumRasterSanitizationOnly",
        "workload": "syntheticOnePageTextPdf",
        "inputBytes": len(source),
        "outputBytesMin": min(output_sizes),
        "outputBytesMax": max(output_sizes),
        "sampleCount": samples,
        "discardedWarmupRuns": 1,
        "medianMilliseconds": round(statistics.median(ordered) / 1_000_000, 3),
        "p90Milliseconds": round(ordered[math.ceil(samples * 0.9) - 1] / 1_000_000, 3),
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--samples", type=int, default=3)
    args = parser.parse_args(argv)
    try:
        report = benchmark(args.samples)
    except (ValueError, RuntimeError) as exc:
        parser.exit(1, str(exc) + "\n")
    print(json.dumps(report, sort_keys=True, allow_nan=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
