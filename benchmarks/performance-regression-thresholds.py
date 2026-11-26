#!/usr/bin/env python3
"""Compare paired, same-runner medium-PDF measurements against explicit gates.

Standalone CI evidence only: no scanner, user document, settings or opening path.
A breach must repeat in two alternating baseline/candidate rounds to fail.
"""

import argparse
import json
import math
from pathlib import Path
import sys

ROUNDS = 2
SAMPLES = 5
MEDIAN_FACTOR = 1.5
MEDIAN_GRACE_MS = 15.0
P95_FACTOR = 1.75
P95_GRACE_MS = 25.0
ERROR = "Performance regression evidence is invalid or incomplete."
FIELDS = frozenset({
  "workload", "stage", "pages", "inputBytes", "warmups", "runs",
  "medianMs", "p95Ms", "authorizesOpen",
})


def _unique_fields(pairs):
  result = {}
  for name, value in pairs:
    if name in result:
      raise ValueError(ERROR)
    result[name] = value
  return result


def _invalid_constant(_value):
  raise ValueError(ERROR)


def read_measurement(path):
  """Require the exact synthetic workload and complete, finite measurements."""
  try:
    with Path(path).open(encoding="utf-8") as source:
      report = json.load(source, object_pairs_hook=_unique_fields,
                         parse_constant=_invalid_constant)
  except (OSError, UnicodeError, json.JSONDecodeError, ValueError) as exc:
    raise ValueError(ERROR) from exc
  if (type(report) is not dict or set(report) != FIELDS or
      report["workload"] != "synthetic-medium-pdf" or
      report["stage"] != "isolated-pdf-structure-analysis" or
      type(report["pages"]) is not int or report["pages"] != 128 or
      type(report["inputBytes"]) is not int or
      not 4 * 1024 * 1024 <= report["inputBytes"] <= 8 * 1024 * 1024 or
      type(report["warmups"]) is not int or report["warmups"] != 1 or
      type(report["runs"]) is not int or report["runs"] != SAMPLES or
      report["authorizesOpen"] is not False):
    raise ValueError(ERROR)
  for metric in ("medianMs", "p95Ms"):
    value = report[metric]
    if (type(value) not in (int, float) or not math.isfinite(value) or
        value <= 0):
      raise ValueError(ERROR)
  if report["p95Ms"] < report["medianMs"]:
    raise ValueError(ERROR)
  return report


def compare(baselines, candidates):
  """Return a complete, non-authorizing decision; never accept partial rounds."""
  if len(baselines) != ROUNDS or len(candidates) != ROUNDS:
    raise ValueError(ERROR)
  pairs = [(read_measurement(baselines[i]), read_measurement(candidates[i]))
           for i in range(ROUNDS)]
  if len({report["inputBytes"] for pair in pairs for report in pair}) != 1:
    raise ValueError(ERROR)

  rounds = []
  for index, (base, head) in enumerate(pairs, 1):
    limit_median = max(base["medianMs"] * MEDIAN_FACTOR,
                       base["medianMs"] + MEDIAN_GRACE_MS)
    limit_p95 = max(base["p95Ms"] * P95_FACTOR,
                    base["p95Ms"] + P95_GRACE_MS)
    rounds.append({
      "round": index,
      "baselineMedianMs": base["medianMs"],
      "candidateMedianMs": head["medianMs"],
      "medianLimitMs": round(limit_median, 3),
      "medianExceeded": head["medianMs"] > limit_median,
      "baselineP95Ms": base["p95Ms"],
      "candidateP95Ms": head["p95Ms"],
      "p95LimitMs": round(limit_p95, 3),
      "p95Exceeded": head["p95Ms"] > limit_p95,
    })

  confirmed = any(all(item[key] for item in rounds)
                  for key in ("medianExceeded", "p95Exceeded"))
  isolated = any(item["medianExceeded"] or item["p95Exceeded"]
                 for item in rounds)
  return {
    "schemaVersion": 1,
    "scope": "pairedSyntheticMediumPdfStructureAnalysisOnly",
    "authorizesOpen": False,
    "thresholds": {
      "median": {"maximumFactor": MEDIAN_FACTOR, "graceMs": MEDIAN_GRACE_MS},
      "p95": {"maximumFactor": P95_FACTOR, "graceMs": P95_GRACE_MS},
      "confirmationRounds": ROUNDS,
    },
    "status": "regression" if confirmed else (
      "unconfirmed" if isolated else "pass"),
    "rounds": rounds,
  }


def main(argv=None):
  parser = argparse.ArgumentParser(description=__doc__)
  parser.add_argument("--baseline", nargs=ROUNDS, required=True,
                      metavar=("BASELINE_1", "BASELINE_2"))
  parser.add_argument("--candidate", nargs=ROUNDS, required=True,
                      metavar=("CANDIDATE_1", "CANDIDATE_2"))
  args = parser.parse_args(argv)
  try:
    result = compare(args.baseline, args.candidate)
  except ValueError:
    parser.exit(2, ERROR + "\n")
  print(json.dumps(result, sort_keys=True, allow_nan=False))
  if result["status"] == "regression":
    return 1
  if result["status"] == "unconfirmed":
    print("Unconfirmed single-round threshold breach; investigate runner noise.",
          file=sys.stderr)
  return 0


if __name__ == "__main__":
  raise SystemExit(main())
