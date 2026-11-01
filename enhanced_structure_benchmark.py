#!/usr/bin/env python3
"""Benchmark the real Enhanced PDF structure stage on generated, inert PDFs.

Not an antivirus scan, verdict, or opening authorization.
"""
import argparse
from io import BytesIO
import json
import math
import statistics
import subprocess
import sys

from enhanced_analysis_findings import AnalysisStage, StageAnalysis, StageOutcome
from enhanced_analysis_timing import AdditionalAnalysisTimer
from pdf_structure_parser import MAX_STRUCTURE_INPUT_BYTES, PDFStructure, parse_pdf_structure
from reference_pdf_collection import REFERENCE_PDFS

CASE_PAGES = {"one-page-text": 1, "thirty-two-pages": 32}
MIN_SAMPLES = 3
MAX_SAMPLES = 10
WORKER_TIMEOUT_SECONDS = 30
ERROR = "Enhanced structural benchmark failed or was incomplete; no measurements recorded."


def fixture(case):
    """Generate fixed harmless bytes in memory, outside the timed interval."""
    if case not in CASE_PAGES:
        raise ValueError("Unknown benchmark case")
    if case == "one-page-text":
        data = REFERENCE_PDFS[0].content
    else:
        from pypdf import PdfWriter
        writer = PdfWriter()
        for _ in range(CASE_PAGES[case]):
            writer.add_blank_page(width=612, height=792)
        output = BytesIO()
        writer.write(output)
        data = output.getvalue()
    if (type(data) is not bytes or not data.startswith(b"%PDF-") or
            not data.rstrip().endswith(b"%%EOF") or
            not 0 < len(data) < MAX_STRUCTURE_INPUT_BYTES):
        raise RuntimeError(ERROR)
    return data


def measure_worker(case, *, analyzer=parse_pdf_structure, clock=None):
    """Time only real structural inspection, not fixture construction/startup."""
    data = fixture(case)
    stage = AnalysisStage.pdfStructure
    timer = AdditionalAnalysisTimer((stage,), clock=clock)

    def inspect():
        parsed = analyzer(data)
        if type(parsed) is not PDFStructure or parsed.page_count != CASE_PAGES[case]:
            raise RuntimeError(ERROR)
        return StageAnalysis(stage, StageOutcome.completed)

    timer.measure(stage, inspect)
    snapshot = timer.snapshot()
    if (not snapshot.timing_complete or snapshot.authorizes_open or
            len(snapshot.stages) != 1 or
            snapshot.stages[0].elapsed_nanoseconds <= 0):
        raise RuntimeError(ERROR)
    return {
        "case": case, "pages": CASE_PAGES[case], "inputBytes": len(data),
        "stage": stage.value, "outcome": StageOutcome.completed.value,
        "elapsedNanoseconds": snapshot.stages[0].elapsed_nanoseconds,
        "authorizesOpen": False,
    }


def benchmark(case="all", samples=5, *, runner=subprocess.run):
    """Discard warmups and require all bounded worker samples to be valid."""
    if case not in (*CASE_PAGES, "all"):
        raise ValueError("Unknown benchmark case")
    if type(samples) is not int or not MIN_SAMPLES <= samples <= MAX_SAMPLES:
        raise ValueError("Samples must be between three and ten")
    summary = []
    for name in (CASE_PAGES if case == "all" else (case,)):
        timings = []
        fixture_bytes = None
        for index in range(samples + 1):
            try:
                completed = runner(
                    [sys.executable, __file__, "--worker", "--case", name],
                    capture_output=True, text=True, check=False,
                    timeout=WORKER_TIMEOUT_SECONDS,
                )
                if completed.returncode != 0 or completed.stderr.strip():
                    raise RuntimeError(ERROR)
                record = json.loads(completed.stdout)
                if (type(record) is not dict or
                        set(record) != {"case", "pages", "inputBytes", "stage",
                                        "outcome", "elapsedNanoseconds", "authorizesOpen"} or
                        record["case"] != name or
                        type(record["pages"]) is not int or
                        record["pages"] != CASE_PAGES[name] or
                        type(record["inputBytes"]) is not int or
                        not 0 < record["inputBytes"] < MAX_STRUCTURE_INPUT_BYTES or
                        record["stage"] != AnalysisStage.pdfStructure.value or
                        record["outcome"] != StageOutcome.completed.value or
                        record["authorizesOpen"] is not False or
                        type(record["elapsedNanoseconds"]) is not int or
                        record["elapsedNanoseconds"] <= 0 or
                        (fixture_bytes is not None and
                         fixture_bytes != record["inputBytes"])):
                    raise RuntimeError(ERROR)
                fixture_bytes = record["inputBytes"]
            except Exception:
                # Suppress partial data, worker errors, paths, and PDF content.
                raise RuntimeError(ERROR) from None
            if index:
                timings.append(record["elapsedNanoseconds"])
        ordered = sorted(timings)
        summary.append({
            "case": name, "pages": CASE_PAGES[name],
            "inputBytes": fixture_bytes, "samples": samples,
            "medianMilliseconds": round(statistics.median(ordered) / 1_000_000, 3),
            "p90Milliseconds": round(ordered[math.ceil(samples * 0.9) - 1] / 1_000_000, 3),
        })
    return {"schemaVersion": 1, "scope": "enhancedPdfStructureStageOnly",
            "discardedWarmupRunsPerCase": 1, "authorizesOpen": False,
            "results": summary}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--case", choices=(*CASE_PAGES, "all"), default="all")
    parser.add_argument("--samples", type=int, default=5)
    parser.add_argument("--worker", action="store_true", help=argparse.SUPPRESS)
    args = parser.parse_args(argv)
    try:
        if args.worker:
            if args.case == "all" or args.samples != 5:
                raise RuntimeError(ERROR)
            result = measure_worker(args.case)
        else:
            result = benchmark(args.case, args.samples)
        print(json.dumps(result, sort_keys=True, allow_nan=False))
    except Exception:
        parser.exit(1, ERROR + "\n")


if __name__ == "__main__":
    main()
