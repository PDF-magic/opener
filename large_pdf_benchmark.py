#!/usr/bin/env python3
"""opener-1075: benchmark only generated, inert large PDFs in isolated workers.

This is parsing workload evidence, never a ClamAV verdict or permission to open.
"""
import argparse
from importlib.metadata import version
from io import BytesIO
import json
import resource
import statistics
import subprocess
import sys
from time import perf_counter

from large_valid_pdf_corpus import LARGE_PDF_MIN_BYTES, LARGE_VALID_PDF_CASES, build_large_valid_pdf


MAX_RUNS = 5
WORKER_TIMEOUT = 90
INCOMPLETE = "Incomplete large PDF benchmark; no results recorded."
CASE_NAMES = tuple(case.identifier for case in LARGE_VALID_PDF_CASES)


def validate(case_name, runs):
  if case_name not in (*CASE_NAMES, "all"):
    raise ValueError("Unknown fixed corpus case")
  if type(runs) is not int or not 1 <= runs <= MAX_RUNS:
    raise ValueError("Runs must be between one and five")


def worker(case_name):
  if case_name not in CASE_NAMES:
    raise ValueError("Workers require a fixed corpus case")
  from pypdf import PdfReader

  case = next(item for item in LARGE_VALID_PDF_CASES if item.identifier == case_name)
  started = perf_counter()
  document = build_large_valid_pdf(case)
  generated = perf_counter()
  if len(document) <= LARGE_PDF_MIN_BYTES:
    raise ValueError("Generated document did not reach the large-PDF boundary")

  reader = PdfReader(BytesIO(document), strict=True)
  if reader.is_encrypted or len(reader.pages) != case.page_count:
    raise ValueError("Generated PDF did not parse as the expected document")
  content_bytes = 0
  for index, page in enumerate(reader.pages):
    content = page.get_contents().get_data()
    prefix = (f"BT /F1 12 Tf 72 720 Td (Large valid PDF page {index + 1}) Tj ET\n").encode()
    if not content.startswith(prefix) or len(content) != len(prefix) + case.padding_per_page:
      raise ValueError("Parsed PDF stream does not match the inert corpus")
    content_bytes += len(content)
  parsed = perf_counter()

  peak = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
  rss_mib = peak / (1024 * 1024 if sys.platform == "darwin" else 1024)
  return {
    "case": case_name,
    "pages": case.page_count,
    "input_bytes": len(document),
    "traversed_stream_bytes": content_bytes,
    "parser": "pypdf",
    "parser_version": version("pypdf"),
    "generate_ms": round((generated - started) * 1000, 3),
    "parse_and_traverse_ms": round((parsed - generated) * 1000, 3),
    "peak_process_rss_mib": round(rss_mib, 2),
  }


def measure(case_name="all", runs=3, *, runner=subprocess.run):
  validate(case_name, runs)
  chosen = CASE_NAMES if case_name == "all" else (case_name,)
  results = []
  for identifier in chosen:
    samples = []
    for _ in range(runs):
      try:
        completed = runner(
          [sys.executable, __file__, "--worker", "--case", identifier, "--runs", "1"],
          capture_output=True, text=True, check=False, timeout=WORKER_TIMEOUT,
        )
        if completed.returncode != 0 or completed.stderr.strip():
          raise RuntimeError(INCOMPLETE)
        sample = json.loads(completed.stdout)
        if (sample.get("case") != identifier or sample.get("pages") !=
            next(c.page_count for c in LARGE_VALID_PDF_CASES if c.identifier == identifier) or
            sample.get("input_bytes", 0) <= LARGE_PDF_MIN_BYTES or
            sample.get("traversed_stream_bytes", 0) <= LARGE_PDF_MIN_BYTES or
            sample.get("parser") != "pypdf" or
            not all(type(sample.get(key)) in (float, int) and sample[key] >= 0
                    for key in ("generate_ms", "parse_and_traverse_ms", "peak_process_rss_mib")) or
            sample["peak_process_rss_mib"] <= 0):
          raise RuntimeError(INCOMPLETE)
      except (OSError, subprocess.TimeoutExpired, ValueError, TypeError, KeyError,
              json.JSONDecodeError) as error:
        raise RuntimeError(INCOMPLETE) from error
      samples.append(sample)

    results.append({
      "case": identifier,
      "pages": samples[0]["pages"],
      "input_bytes": samples[0]["input_bytes"],
      "traversed_stream_bytes": samples[0]["traversed_stream_bytes"],
      "parser": "pypdf",
      "parser_version": samples[0]["parser_version"],
      "runs": runs,
      "median_generate_ms": round(statistics.median(s["generate_ms"] for s in samples), 3),
      "median_parse_and_traverse_ms": round(statistics.median(
        s["parse_and_traverse_ms"] for s in samples), 3),
      "max_process_rss_mib": max(s["peak_process_rss_mib"] for s in samples),
    })
  return {"scope": "syntheticLargePDFStrictParsing", "authorizes_open": False,
          "results": results}


def main():
  parser = argparse.ArgumentParser(description=__doc__)
  parser.add_argument("--case", choices=(*CASE_NAMES, "all"), default="all")
  parser.add_argument("--runs", type=int, default=3)
  parser.add_argument("--worker", action="store_true", help=argparse.SUPPRESS)
  args = parser.parse_args()
  try:
    validate(args.case, args.runs)
    if args.worker:
      if args.case == "all" or args.runs != 1:
        raise ValueError("Worker requires one case and one run")
      print(json.dumps(worker(args.case), sort_keys=True))
    else:
      print(json.dumps(measure(args.case, args.runs), sort_keys=True, indent=2))
  except (ImportError, RuntimeError, ValueError, OSError) as error:
    parser.exit(1, INCOMPLETE + "\n")


if __name__ == "__main__":
  main()
