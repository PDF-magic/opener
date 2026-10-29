"""Time-bounded opt-in PDF structure inspection, independent of the live scan gate.

Only a trusted Python worker can parse supplied bytes. The existing process
supervisor enforces a monotonic wall deadline, kills the whole worker process
group and bounds output while reading it. No PDF path, command or environment
is selected from untrusted content; a result never authorizes opening.
"""

import json
from pathlib import Path
import sys

from maximum_process_termination import MAX_WALL_SECONDS, run_limited_worker
from pdf_structure_parser import MAX_STRUCTURE_INPUT_BYTES, PDFStructure
from protection_policy_definitions import PolicyControl
from protection_stage_time_limits import STAGE_MAXIMUM_SECONDS


# The existing trusted group-killing supervisor supports at most 30 seconds.
# This conservative cap stays below the planned 120-second structure budget.
ANALYSIS_TIMEOUT_SECONDS = min(
  MAX_WALL_SECONDS, STAGE_MAXIMUM_SECONDS[PolicyControl.PDF_STRUCTURE_VALIDATION]
)
BLOCK_MESSAGE = "Timed PDF structure analysis could not complete; opening was stopped."

_ENV = {
  "PATH": "/usr/bin:/bin",
  "HOME": "/nonexistent",
  "LANG": "C",
  "PYTHONDONTWRITEBYTECODE": "1",
  "PYTHONNOUSERSITE": "1",
}


class TimedPDFAnalysisError(RuntimeError):
  """A blocked or incomplete analysis, with no source bytes or paths."""


def _worker_command():
  worker = Path(__file__).resolve().with_name("timed_pdf_structure_worker.py")
  return (sys.executable, "-I", "-B", str(worker))


def _unique_pairs(pairs):
  record = {}
  for key, value in pairs:
    if key in record:
      raise ValueError("Duplicate field")
    record[key] = value
  return record


def parse_pdf_structure_timed(contents: bytes) -> PDFStructure:
  """Parse only in a supervised child, failing closed on timeout or any error.

  Unlike the foundational in-process parser this entry point guarantees a
  finite execution window, for future callers handling untrusted PDFs.
  Neither function is wired into the installed Built-in scanner.
  """
  if type(contents) is not bytes or not 0 < len(contents) <= MAX_STRUCTURE_INPUT_BYTES:
    raise TimedPDFAnalysisError(BLOCK_MESSAGE)

  try:
    response = run_limited_worker(
      _worker_command(), contents,
      timeout_seconds=ANALYSIS_TIMEOUT_SECONDS,
      environment=_ENV.copy(),
    )
    record = json.loads(response, object_pairs_hook=_unique_pairs)
    if (type(record) is not dict or
        set(record) != {"schemaVersion", "pdfVersion", "pageCount", "authorizesOpen"} or
        type(record["schemaVersion"]) is not int or record["schemaVersion"] != 1 or
        type(record["pdfVersion"]) is not str or
        type(record["pageCount"]) is not int or
        record["authorizesOpen"] is not False):
      raise TimedPDFAnalysisError(BLOCK_MESSAGE)
    result = PDFStructure(record["pdfVersion"], record["pageCount"])
    if result.to_dict() != record:
      raise TimedPDFAnalysisError(BLOCK_MESSAGE)
    return result
  except Exception:
    # Never return child diagnostics, untrusted document content or paths.
    raise TimedPDFAnalysisError(BLOCK_MESSAGE) from None
