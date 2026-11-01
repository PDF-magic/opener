#!/usr/bin/env python3
"""Validate the evidence-backed performance snapshot without network access."""

from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parent.parent
REPORT = ROOT / "docs" / "performance" / "observed-results.md"
INDEX = ROOT / "docs" / "README.md"
REQUIRED = {
  "small-text": "small_text_pdf_benchmark.py",
  "medium-pdf": "medium_pdf_benchmark.py",
  "embedded-objects": "many_embedded_objects_benchmark.py",
  "enhanced-structure": "enhanced_structure_benchmark.py",
  "scanner-startup": "scanner_startup_benchmark.py",
  "peak-memory": "peak_memory_benchmark.py",
  "cpu-usage": "cpu_usage_benchmark.py",
  "cold-warm": "cold_warm_scan_benchmark.py",
  "app-launch": "app_launch_benchmark.py",
  "ui-responsiveness": "ui_responsiveness_benchmark.py",
}
ROW = re.compile(
  r"^\| \x60([a-z0-9-]+)\x60 \| ([^|]+) \| ([1-9]\d*(?: pairs| cycles)?) \| "
  r"([^|]+) \| \[CI job\]\(https://github\.com/PDF-magic/opener/"
  r"actions/runs/([1-9]\d*)/job/([1-9]\d*)\) \|$"
)
METRIC = re.compile(r"(\d+(?:\.\d+)?)\s+(ms|MiB)\b")


def validate(document):
  errors = []
  seen = set()
  for line in document.splitlines():
    if not line.startswith("| \x60"):
      continue
    match = ROW.fullmatch(line)
    if not match:
      errors.append("Malformed benchmark row or missing GitHub job evidence")
      continue
    name, workload, samples, results, run, job = match.groups()
    if name in seen:
      errors.append(f"Duplicate benchmark row: {name}")
    seen.add(name)
    if not workload.strip() or not results.strip():
      errors.append(f"Incomplete workload or results: {name}")
    measurements = METRIC.findall(results)
    if not measurements or any(float(value) <= 0 for value, _ in measurements):
      errors.append(f"No positive measured timing or memory for {name}")
  if seen != REQUIRED.keys():
    errors.append(f"Benchmark rows differ from expected set: missing={sorted(REQUIRED.keys() - seen)} extra={sorted(seen - REQUIRED.keys())}")
  return errors


def check():
  errors = validate(REPORT.read_text(encoding="utf-8"))
  if "(performance/observed-results.md)" not in INDEX.read_text(encoding="utf-8"):
    errors.append("Developer documentation index does not link benchmark results")
  for name, source in REQUIRED.items():
    if not (ROOT / source).is_file():
      errors.append(f"Missing source benchmark for {name}: {source}")
  return errors


if __name__ == "__main__":
  errors = check()
  for error in errors:
    print(error, file=sys.stderr)
  if errors:
    raise SystemExit(1)
  print("Documented benchmark rows and GitHub evidence links verified.")
