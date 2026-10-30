#!/usr/bin/env python3
"""opener-0434: prove timed PDF analysis is actually killed when overdue."""

from io import BytesIO
from pathlib import Path
import os
import subprocess
import sys
import time
import unittest
from unittest.mock import patch

from pypdf import PdfWriter

from maximum_process_termination import MAX_WALL_SECONDS
from pdf_structure_parser import PDFStructure, MAX_STRUCTURE_INPUT_BYTES
from protection_policy_definitions import PolicyControl
from protection_stage_time_limits import STAGE_MAXIMUM_SECONDS
from reference_pdf_collection import REFERENCE_PDFS
import timed_pdf_structure_analysis as timed


ROOT = Path(__file__).resolve().parents[2]


def make_pdf():
  writer = PdfWriter()
  writer.add_blank_page(width=200, height=200)
  stream = BytesIO()
  writer.write(stream)
  return stream.getvalue()


class TimedPDFStructureTests(unittest.TestCase):
  def test_real_child_parses_reference_corpus_and_generated_document(self):
    for sample in REFERENCE_PDFS:
      with self.subTest(sample=sample.identifier):
        self.assertEqual(
          timed.parse_pdf_structure_timed(sample.content),
          PDFStructure("1.4", 1),
        )
    self.assertEqual(timed.parse_pdf_structure_timed(make_pdf()).page_count, 1)

  def test_uses_trusted_isolated_process_and_existing_time_policy(self):
    actual = timed.run_limited_worker
    calls = []

    def capture(command, contents, **kwargs):
      calls.append((command, contents, kwargs))
      return actual(command, contents, **kwargs)

    contents = make_pdf()
    with patch.object(timed, "run_limited_worker", side_effect=capture):
      result = timed.parse_pdf_structure_timed(contents)
    self.assertEqual(result.page_count, 1)
    command, input_data, options = calls[0]
    self.assertIs(input_data, contents)
    self.assertEqual(command[:3], (sys.executable, "-I", "-B"))
    self.assertTrue(command[-1].endswith("timed_pdf_structure_worker.py"))
    self.assertEqual(
      options["timeout_seconds"],
      timed.ANALYSIS_TIMEOUT_SECONDS,
    )
    self.assertGreater(timed.ANALYSIS_TIMEOUT_SECONDS, 0)
    self.assertLessEqual(timed.ANALYSIS_TIMEOUT_SECONDS, MAX_WALL_SECONDS)
    self.assertLessEqual(
      timed.ANALYSIS_TIMEOUT_SECONDS,
      STAGE_MAXIMUM_SECONDS[PolicyControl.PDF_STRUCTURE_VALIDATION],
    )
    self.assertEqual(
      set(options["environment"]),
      {"PATH", "HOME", "LANG", "PYTHONDONTWRITEBYTECODE", "PYTHONNOUSERSITE"},
    )

  @unittest.skipUnless(os.name == "posix", "POSIX process-group timeout")
  def test_real_deadline_kills_hung_analysis_process(self):
    # Deliberate trusted test command cannot read the input or finish.
    # The real worker supervisor must kill it, not merely check time later.
    with (
      patch.object(timed, "ANALYSIS_TIMEOUT_SECONDS", 1),
      patch.object(timed, "_worker_command", return_value=(
        sys.executable, "-I", "-B", "-c", "import time;time.sleep(20)"
      )),
    ):
      started = time.monotonic()
      with self.assertRaises(timed.TimedPDFAnalysisError) as failure:
        timed.parse_pdf_structure_timed(make_pdf())
      self.assertLess(time.monotonic() - started, 6)
    self.assertEqual(str(failure.exception), timed.BLOCK_MESSAGE)

  def test_bad_inputs_refused_before_worker_launch(self):
    with patch.object(timed, "run_limited_worker") as invoke:
      for contents in (None, "", b"", bytearray(make_pdf()), True,
                       b"X" * (MAX_STRUCTURE_INPUT_BYTES + 1)):
        with self.subTest(kind=type(contents).__name__):
          with self.assertRaises(timed.TimedPDFAnalysisError):
            timed.parse_pdf_structure_timed(contents)
      invoke.assert_not_called()

  def test_invalid_pdf_and_worker_failures_cannot_be_clean(self):
    for contents in (b"%PDF-1.4\n/private/secret.pdf", b"not a PDF"):
      with self.subTest(input=contents[:8]):
        with self.assertRaises(timed.TimedPDFAnalysisError) as caught:
          timed.parse_pdf_structure_timed(contents)
        self.assertEqual(str(caught.exception), timed.BLOCK_MESSAGE)
        self.assertNotIn("secret", str(caught.exception))
    failures = (
      subprocess.TimeoutExpired("private", 1),
      OSError("/private/document"),
      RuntimeError("secret contents"),
    )
    for exception in failures:
      with self.subTest(type=type(exception).__name__), patch.object(
        timed, "run_limited_worker", side_effect=exception
      ):
        with self.assertRaises(timed.TimedPDFAnalysisError) as caught:
          timed.parse_pdf_structure_timed(make_pdf())
        self.assertEqual(str(caught.exception), timed.BLOCK_MESSAGE)

  def test_invalid_or_spoofed_child_responses_fail_closed(self):
    baseline = b'{"schemaVersion":1,"pdfVersion":"1.4","pageCount":1,"authorizesOpen":false}'
    for response in (
      b"", b"not json", b"X" * 4097,
      baseline.replace(b"false", b"true"),
      baseline.replace(b'"pageCount":1', b'"pageCount":true'),
      baseline.replace(b'"schemaVersion":1', b'"schemaVersion":2'),
      baseline.replace(b'"pdfVersion":"1.4"', b'"pdfVersion":"3.0"'),
      baseline[:-1] + b',"extra":5}',
      baseline.replace(b'"pageCount":1', b'"pageCount":1,"pageCount":2'),
    ):
      with self.subTest(output=response[:35]), patch.object(
        timed, "run_limited_worker", return_value=response
      ):
        with self.assertRaises(timed.TimedPDFAnalysisError):
          timed.parse_pdf_structure_timed(make_pdf())

  def test_ci_includes_timeout_tests_but_scanner_is_unmodified(self):
    ci = (ROOT / ".github/workflows/ci.yml").read_text(encoding="utf-8")
    scanner = (ROOT / "scan-and-open.py").read_text(encoding="utf-8")
    source = (ROOT / "timed_pdf_structure_analysis.py").read_text(
      encoding="utf-8"
    )
    self.assertIn("python3 tests/general/timed-pdf-structure-analysis.py -v", ci)
    self.assertNotIn("timed_pdf_structure_analysis", scanner)
    self.assertNotIn("timed_pdf_structure_worker", scanner)
    self.assertNotIn("remove_quarantine(", source)
    self.assertNotIn("launch_clean_file(", source)
    from protection_policy_definitions import PROTECTION_POLICIES, ProtectionProfileID
    self.assertFalse(PROTECTION_POLICIES[ProtectionProfileID.ENHANCED].selectable)


if __name__ == "__main__":
  unittest.main()
