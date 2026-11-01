#!/usr/bin/env python3
"""Opt-in benchmark of a small text PDF through supervised structure analysis.

Measures the actual, time-limited structure-analysis worker, not antivirus
scanning, quarantine removal, PDF rendering, or end-to-end opening latency.
Never reads user documents, runs the scanner, or authorizes opening.
"""

import argparse
import json
import math
import statistics
import time

from reference_pdf_collection import REFERENCE_PDFS
from timed_pdf_structure_analysis import parse_pdf_structure_timed

MIN_SAMPLES = 5
MAX_SAMPLES = 20
ERROR = "Small PDF benchmark failed or was incomplete; no measurements were recorded."


def fixture():
    """Reuse the repository's deterministic, valid, one-page text-based PDF."""
    pdf = REFERENCE_PDFS[0].content
    if (type(pdf) is not bytes or not 0 < len(pdf) < 4096 or
            not pdf.startswith(b"%PDF-1.4\n") or
            b"BT /F1 12 Tf" not in pdf or b"(Clean baseline) Tj" not in pdf or
            not pdf.endswith(b"%%EOF\n")):
        raise RuntimeError(ERROR)
    return pdf


def benchmark(samples=5, *, analyzer=parse_pdf_structure_timed,
              clock=time.perf_counter_ns):
    """Return complete real durations only, discarding one warmup invocation."""
    if type(samples) is not int or not MIN_SAMPLES <= samples <= MAX_SAMPLES:
        raise ValueError("Choose 5 to 20 completed benchmark samples.")
    pdf = fixture()
    durations = []
    for index in range(samples + 1):
        try:
            start = clock()
            result = analyzer(pdf)
            elapsed_ns = clock() - start
            if (type(result.page_count) is not int or result.page_count != 1 or
                    result.pdf_version != "1.4" or
                    type(elapsed_ns) not in (int, float) or
                    not math.isfinite(elapsed_ns) or elapsed_ns <= 0):
                raise RuntimeError(ERROR)
        except Exception:
            # Never expose worker errors, paths, bytes or partial timings.
            raise RuntimeError(ERROR) from None
        if index:
            durations.append(elapsed_ns)
    ordered = sorted(durations)
    p90 = ordered[math.ceil(len(ordered) * 0.9) - 1]
    return {
        "schemaVersion": 1,
        "scope": "timedPdfStructureAnalysisOnly",
        "fixture": "syntheticOnePageTextPdf",
        "fixtureBytes": len(pdf),
        "sampleCount": samples,
        "discardedWarmupRuns": 1,
        "medianMilliseconds": round(statistics.median(ordered) / 1_000_000, 3),
        "p90Milliseconds": round(p90 / 1_000_000, 3),
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--samples", type=int, default=5)
    args = parser.parse_args(argv)
    try:
        report = benchmark(args.samples)
    except (ValueError, RuntimeError) as exc:
        parser.exit(1, str(exc) + "\n")
    print(json.dumps(report, sort_keys=True, allow_nan=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
