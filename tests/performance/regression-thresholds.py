#!/usr/bin/env python3
"""opener-1087: verify paired CI regression gates and scanner noninterference."""

import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from performance_regression_thresholds import (
  MEDIAN_FACTOR, MEDIAN_GRACE_MS, P95_FACTOR, P95_GRACE_MS,
  compare, main, read_measurement,
)

ROOT = Path(__file__).resolve().parents[2]


def record(median=40.0, p95=60.0, **changes):
  result = {
    "workload": "synthetic-medium-pdf",
    "stage": "isolated-pdf-structure-analysis",
    "pages": 128,
    "inputBytes": 4_200_000,
    "warmups": 1,
    "runs": 5,
    "medianMs": median,
    "p95Ms": p95,
    "authorizesOpen": False,
  }
  result.update(changes)
  return result


class RegressionThresholdTests(unittest.TestCase):
  def setUp(self):
    self.folder = tempfile.TemporaryDirectory(prefix="perf-gates-")
    self.addCleanup(self.folder.cleanup)
    self.counter = 0

  def save(self, data):
    self.counter += 1
    path = Path(self.folder.name) / f"round-{self.counter}.json"
    path.write_text(json.dumps(data), encoding="utf-8")
    return str(path)

  def pairs(self, baseline, candidate):
    return ([self.save(item) for item in baseline],
            [self.save(item) for item in candidate])

  def test_thresholds_are_explicit_and_separate_for_median_and_tail(self):
    self.assertEqual((MEDIAN_FACTOR, MEDIAN_GRACE_MS), (1.5, 15.0))
    self.assertEqual((P95_FACTOR, P95_GRACE_MS), (1.75, 25.0))
    base, head = self.pairs([record(), record()],
                            [record(50, 80), record(50, 80)])
    result = compare(base, head)
    self.assertEqual(result["status"], "pass")
    self.assertEqual(result["rounds"][0]["medianLimitMs"], 60)
    self.assertEqual(result["rounds"][0]["p95LimitMs"], 105)
    self.assertFalse(result["authorizesOpen"])

  def test_repeated_median_breach_blocks(self):
    base, head = self.pairs([record(), record()],
                            [record(70, 75), record(61, 80)])
    result = compare(base, head)
    self.assertEqual(result["status"], "regression")
    self.assertTrue(all(r["medianExceeded"] for r in result["rounds"]))

  def test_repeated_tail_breach_blocks_even_if_median_passes(self):
    base, head = self.pairs([record(), record()],
                            [record(40, 106), record(45, 115)])
    self.assertEqual(compare(base, head)["status"], "regression")

  def test_one_noisy_round_does_not_fail_and_exact_limit_passes(self):
    base, head = self.pairs([record(), record()],
                            [record(61, 105), record(60, 105)])
    self.assertEqual(compare(base, head)["status"], "unconfirmed")
    base, head = self.pairs([record(), record()],
                            [record(60, 105), record(60, 105)])
    self.assertEqual(compare(base, head)["status"], "pass")

  def test_incomplete_or_incomparable_evidence_is_rejected(self):
    good = record()
    invalid = [
      dict(good, authorizesOpen=True), dict(good, inputBytes=0),
      dict(good, pages=True), dict(good, runs=3),
      dict(good, warmups=False), dict(good, medianMs=0),
      dict(good, medianMs=True), dict(good, p95Ms=float("inf")),
      dict(good, medianMs=float("nan")), dict(good, p95Ms=20),
      dict(good, stage="scanner"), dict(good, workload="different"),
      dict(good, extra="unexpected"),
    ]
    for bad in invalid:
      with self.subTest(bad=bad), self.assertRaises(ValueError):
        read_measurement(self.save(bad))
    for raw in ('{"workload":"x","workload":"y"}', "[]", "NaN", "{"):
      path = Path(self.folder.name) / "invalid.json"
      path.write_text(raw, encoding="utf-8")
      with self.assertRaises(ValueError):
        read_measurement(path)
    base, head = self.pairs([good, good], [good, record(inputBytes=4_200_001)])
    with self.assertRaises(ValueError):
      compare(base, head)
    with self.assertRaises(ValueError):
      compare(base[:1], head)

  def test_cli_exit_codes_and_no_partial_results(self):
    base, head = self.pairs([record(), record()],
                            [record(70, 120), record(75, 130)])
    program = ROOT / "performance_regression_thresholds.py"
    run = subprocess.run(
      [sys.executable, str(program), "--baseline", *base,
       "--candidate", *head], capture_output=True, text=True, timeout=10)
    self.assertEqual(run.returncode, 1)
    self.assertEqual(json.loads(run.stdout)["status"], "regression")
    run = subprocess.run(
      [sys.executable, str(program), "--baseline", *base,
       "--candidate", head[0], "missing.json"],
      capture_output=True, text=True, timeout=10)
    self.assertEqual(run.returncode, 2)
    self.assertFalse(run.stdout)
    self.assertNotIn("missing.json", run.stderr)

  def test_ci_has_real_comparison_and_does_not_touch_live_opening(self):
    workflow = (ROOT / ".github/workflows/performance-regression-thresholds.yml").read_text()
    docs = (ROOT / "docs/performance/regression-thresholds.md").read_text()
    live = (ROOT / "scan-and-open.py").read_text()
    self.assertIn("python3 medium_pdf_benchmark.py --runs 5", workflow)
    self.assertIn("performance_regression_thresholds.py", workflow)
    self.assertIn("cmp -s", workflow)
    self.assertIn("pull_request:", workflow)
    self.assertIn("merge_group:", workflow)
    self.assertIn("if not cached_clean(cache_id):", live)
    self.assertNotIn("performance_regression_thresholds", live)
    self.assertIn("same runner", docs)
    self.assertIn("not end-to-end", docs)


if __name__ == "__main__":
  unittest.main()
