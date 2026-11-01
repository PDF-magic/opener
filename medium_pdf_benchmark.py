#!/usr/bin/env python3
"""Time isolated structure inspection of a generated, inert medium-sized PDF.

This never invokes the installed scanner, releases quarantine, or opens a PDF.
Results are measurements of one optional analysis stage, not end-to-end latency.
"""

import argparse
import json
import math
import statistics
import time

from pdf_parser_memory_benchmark import synthetic_pdf
from pdf_structure_parser import MAX_STRUCTURE_INPUT_BYTES, PDFStructure
from timed_pdf_structure_analysis import parse_pdf_structure_timed


MEDIUM_PAGES = 128
MEDIUM_STREAM_BYTES = 4 * 1024 * 1024
MIN_MEDIUM_BYTES = 4 * 1024 * 1024
MAX_MEDIUM_BYTES = 8 * 1024 * 1024
MAX_RUNS = 10


def build_medium_pdf():
  """Build a deterministic, complete PDF in memory; never read user files."""
  document = synthetic_pdf(MEDIUM_PAGES, MEDIUM_STREAM_BYTES)
  if not MIN_MEDIUM_BYTES <= len(document) <= MAX_MEDIUM_BYTES:
    raise RuntimeError("Generated medium-PDF workload is outside its bounds")
  if len(document) > MAX_STRUCTURE_INPUT_BYTES:
    raise RuntimeError("Generated workload exceeds the isolated parser input limit")
  return document


def benchmark_medium_pdf(*, runs=5, parse=parse_pdf_structure_timed,
                         clock_ns=time.perf_counter_ns):
  """Warm up once, then measure real supervised parsing without speed gates."""
  if type(runs) is not int or not 1 <= runs <= MAX_RUNS:
    raise ValueError("Benchmark run count must be between 1 and 10")
  document = build_medium_pdf()
  samples = []
  for index in range(runs + 1):
    started = clock_ns()
    evidence = parse(document)
    duration = clock_ns() - started
    if (not isinstance(evidence, PDFStructure) or
        evidence.pdf_version != "1.7" or evidence.page_count != MEDIUM_PAGES or
        evidence.to_dict()["authorizesOpen"] is not False):
      raise RuntimeError("Medium-PDF inspection did not return safe expected evidence")
    if type(duration) is not int or duration <= 0:
      raise RuntimeError("Benchmark clock produced an invalid measurement")
    if index:
      samples.append(duration)

  ordered = sorted(samples)
  return {
    "workload": "synthetic-medium-pdf",
    "stage": "isolated-pdf-structure-analysis",
    "pages": MEDIUM_PAGES,
    "inputBytes": len(document),
    "warmups": 1,
    "runs": runs,
    "medianMs": round(statistics.median(ordered) / 1_000_000, 3),
    "p95Ms": round(ordered[math.ceil(0.95 * len(ordered)) - 1] / 1_000_000, 3),
    "authorizesOpen": False,
  }


def main():
  cli = argparse.ArgumentParser(description=__doc__)
  cli.add_argument("--runs", type=int, default=5, help="1–10 measured runs after one warmup")
  args = cli.parse_args()
  if not 1 <= args.runs <= MAX_RUNS:
    cli.error("--runs must be between 1 and 10")
  print(json.dumps(benchmark_medium_pdf(runs=args.runs), sort_keys=True))


if __name__ == "__main__":
  main()
