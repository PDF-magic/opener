#!/usr/bin/env python3
"""opener-1027: exercise real zero-byte files in the PDF security test corpus.

These inert fixtures cannot stand in for valid reference PDFs. The installed
Built-in gate must reject them without accepting a cached verdict or opening
a viewer; the planned structural parser cannot authorize an empty PDF.
"""

from contextlib import ExitStack
import importlib.util
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

from pdf_format_identification import UNDETERMINED, identify_pdf_format
from pdf_structure_parser import (
    PDFStructureFailureCode,
    PDFStructureParseFailure,
    parse_pdf_structure_result,
)
from reference_pdf_collection import REFERENCE_PDFS


ROOT = Path(__file__).resolve().parents[2]
FIXTURES = ROOT / "tests/fixtures"
EMPTY_FILES = ("empty.pdf", "empty.txt", "empty")
sys.dont_write_bytecode = True
spec = importlib.util.spec_from_file_location(
    "empty_corpus_scan_gate", ROOT / "scan-and-open.py"
)
gate = importlib.util.module_from_spec(spec)
spec.loader.exec_module(gate)


class EmptyFileCorpusTests(unittest.TestCase):
    def test_tracked_fixtures_are_regular_files_with_exactly_zero_bytes(self):
        self.assertEqual(len(EMPTY_FILES), len(set(EMPTY_FILES)))
        for name in EMPTY_FILES:
            with self.subTest(name=name):
                path = FIXTURES / name
                self.assertTrue(path.is_file())
                self.assertFalse(path.is_symlink())
                self.assertEqual(path.stat().st_size, 0)
                self.assertEqual(path.read_bytes(), b"")
        self.assertTrue(all(sample.content for sample in REFERENCE_PDFS))

    def test_empty_pdf_never_has_valid_pdf_evidence(self):
        path = FIXTURES / "empty.pdf"
        self.assertIs(identify_pdf_format(path), UNDETERMINED)
        result = parse_pdf_structure_result(path.read_bytes())
        self.assertIs(type(result), PDFStructureParseFailure)
        self.assertIs(result.code, PDFStructureFailureCode.invalidStructure)
        self.assertEqual(result.to_dict()["status"], "failure")
        self.assertIs(result.to_dict()["authorizesOpen"], False)

    def test_every_empty_file_is_rejected_before_cache_scanner_or_handoff(self):
        for name in EMPTY_FILES:
            with self.subTest(name=name):
                path = FIXTURES / name
                with self.assertRaisesRegex(
                    RuntimeError, "zero-length file cannot be scanned"
                ):
                    gate.fingerprint(path)
                with ExitStack() as stack:
                    stack.enter_context(patch.object(
                        gate, "intended_destination",
                        return_value="com.brave.Browser"
                    ))
                    stack.enter_context(patch.object(
                        gate, "pdf_fallback_application", return_value=None
                    ))
                    stack.enter_context(patch.object(
                        gate, "verify_local_file_available"
                    ))
                    stack.enter_context(patch.object(
                        gate, "record_scan_destination"
                    ))
                    cache = stack.enter_context(patch.object(gate, "cached_clean"))
                    scanner = stack.enter_context(patch.object(gate, "run_scan_command"))
                    quarantine = stack.enter_context(
                        patch.object(gate, "remove_quarantine")
                    )
                    launch = stack.enter_context(
                        patch.object(gate, "launch_clean_file")
                    )
                    with self.assertRaisesRegex(
                        RuntimeError, "zero-length file cannot be scanned"
                    ) as failure:
                        gate.scan_and_open(str(path), "/mock-scanner")
                    self.assertIn("opening was stopped", str(failure.exception))
                    cache.assert_not_called()
                    scanner.assert_not_called()
                    quarantine.assert_not_called()
                    launch.assert_not_called()
                self.assertEqual(path.read_bytes(), b"")

    def test_ci_runs_the_empty_file_corpus_regression(self):
        workflow = (ROOT / ".github/workflows/ci.yml").read_text(encoding="utf-8")
        self.assertIn(
            "PYTHONPATH=. python3 tests/general/empty-file-corpus.py -v",
            workflow,
        )


if __name__ == "__main__":
    unittest.main()
