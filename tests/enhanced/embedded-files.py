#!/usr/bin/env python3
"""Real PDF attachment fixtures and fail-closed scan contracts for opener-0285."""

from io import BytesIO
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from pypdf import PdfWriter
from pypdf.generic import ArrayObject, DictionaryObject, NameObject

import enhanced_embedded_files as inspector


def sample_pdf(*attachments):
    writer = PdfWriter()
    writer.add_blank_page(width=200, height=200)
    for name, payload in attachments:
        writer.add_attachment(name, payload)
    output = BytesIO()
    writer.write(output)
    return output.getvalue()


def isolated_associated_file():
    writer = PdfWriter()
    writer.add_blank_page(width=200, height=200)
    writer.add_attachment("document.bin", b"associated payload")
    catalog = writer._root_object
    reference = catalog["/Names"]["/EmbeddedFiles"]["/Names"][1]
    del catalog[NameObject("/Names")]
    catalog[NameObject("/AF")] = ArrayObject([reference])
    output = BytesIO()
    writer.write(output)
    return output.getvalue()


def isolated_annotation_file():
    writer = PdfWriter()
    writer.add_blank_page(width=200, height=200)
    writer.add_attachment("annotation.bin", b"annotation payload")
    catalog = writer._root_object
    reference = catalog["/Names"]["/EmbeddedFiles"]["/Names"][1]
    del catalog[NameObject("/Names")]
    annotation = DictionaryObject({
        NameObject("/Subtype"): NameObject("/FileAttachment"),
        NameObject("/FS"): reference,
    })
    writer.pages[0][NameObject("/Annots")] = ArrayObject([writer._add_object(annotation)])
    output = BytesIO()
    writer.write(output)
    return output.getvalue()


class EmbeddedFileInspectionTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory(prefix="embedded-pdf-test-")
        self.addCleanup(temp.cleanup)
        self.pdf = Path(temp.name) / "fixture.pdf"
        self.database = Path(temp.name) / "signatures"
        self.database.mkdir()

    def inspect(self, payload, result=None, **kwargs):
        self.pdf.write_bytes(payload)
        if result is None:
            result = subprocess.CompletedProcess([], 0, b"stream: OK\n", b"")
        with patch.object(inspector.subprocess, "run", return_value=result) as scan:
            outcome = inspector.inspect_embedded_files(
                self.pdf, "/mock/clamscan", self.database, **kwargs
            )
        return outcome, scan

    def test_extracts_and_scans_actual_payloads_not_names_or_pdf_bytes(self):
        first = b"harmless embedded content"
        second = b"another embedded content"
        outcome, scanner = self.inspect(sample_pdf(("report.txt", first),
                                                    ("second.txt", second)))
        self.assertEqual((outcome.inspected_count, outcome.inspected_bytes),
                         (2, len(first) + len(second)))
        self.assertFalse(outcome.pdf_is_clean)
        self.assertEqual([call.kwargs["input"] for call in scanner.call_args_list],
                         [first, second])
        for call in scanner.call_args_list:
            argv = call.args[0]
            self.assertEqual(argv[0], "/mock/clamscan")
            self.assertIn("--database=" + str(self.database), argv)
            self.assertIn("--alert-encrypted=yes", argv)
            self.assertIn("--stdin", argv)
            self.assertTrue(call.kwargs["capture_output"])
            self.assertEqual(call.kwargs["timeout"],
                             inspector.ATTACHMENT_SCAN_TIMEOUT)

    def test_pdf_without_attachments_does_not_claim_full_pdf_is_safe(self):
        outcome, scan = self.inspect(sample_pdf())
        self.assertEqual(outcome.inspected_count, 0)
        self.assertEqual(outcome.inspected_bytes, 0)
        self.assertFalse(outcome.pdf_is_clean)
        scan.assert_not_called()

    def test_associated_files_are_inspected_even_without_names_tree(self):
        result, scan = self.inspect(isolated_associated_file())
        self.assertEqual(result.inspected_count, 1)
        self.assertEqual(scan.call_args.kwargs["input"], b"associated payload")

    def test_annotation_files_are_inspected_even_without_names_tree(self):
        result, scan = self.inspect(isolated_annotation_file())
        self.assertEqual(result.inspected_count, 1)
        self.assertEqual(scan.call_args.kwargs["input"], b"annotation payload")

    def test_clamav_rejection_warnings_and_incomplete_output_fail_closed(self):
        outcomes = (
            subprocess.CompletedProcess([], 1, b"stream: Malware FOUND", b""),
            subprocess.CompletedProcess([], 2, b"", b"error"),
            subprocess.CompletedProcess([], 0, b"stream: OK", b"warning"),
            subprocess.CompletedProcess([], 0, b"", b""),
            subprocess.CompletedProcess([], 0, b"stream: OK\nskipped", b""),
        )
        for completed in outcomes:
            with self.subTest(code=completed.returncode, stdout=completed.stdout):
                with self.assertRaises(inspector.EmbeddedFileInspectionError) as failure:
                    self.inspect(sample_pdf(("hidden.txt", b"payload")), completed)
                self.assertEqual(str(failure.exception), inspector.BLOCK_MESSAGE)
                self.assertNotIn("hidden.txt", str(failure.exception))

    def test_parser_corruption_missing_dependency_and_encryption_fail_closed(self):
        self.pdf.write_bytes(b"not a PDF")
        with patch.object(inspector.subprocess, "run") as scan:
            with self.assertRaises(inspector.EmbeddedFileInspectionError):
                inspector.inspect_embedded_files(self.pdf, "/mock/clamscan", self.database)
        scan.assert_not_called()
        encrypted = PdfWriter()
        encrypted.add_blank_page(width=200, height=200)
        encrypted.encrypt("password")
        output = BytesIO()
        encrypted.write(output)
        with patch.object(inspector.subprocess, "run") as scan:
            with self.assertRaises(inspector.EmbeddedFileInspectionError):
                self.inspect(output.getvalue())
        scan.assert_not_called()
        with patch.dict(sys.modules, {"pypdf": None}):
            with self.assertRaises(inspector.EmbeddedFileInspectionError):
                inspector.inspect_embedded_files(self.pdf, "/mock/clamscan", self.database)

    def test_document_attachment_and_total_limits_fail_closed(self):
        pdf = sample_pdf(("long.bin", b"a" * 40))
        with self.assertRaises(inspector.EmbeddedFileInspectionError):
            self.inspect(pdf, max_pdf_bytes=16)
        with self.assertRaises(inspector.EmbeddedFileInspectionError):
            self.inspect(pdf, max_attachment_bytes=16)
        with self.assertRaises(inspector.EmbeddedFileInspectionError):
            self.inspect(pdf, max_total_bytes=16)
        many = sample_pdf(("a", b"x"), ("b", b"y"))
        with self.assertRaises(inspector.EmbeddedFileInspectionError):
            self.inspect(many, max_attachments=1)

    def test_no_weakening_or_side_effects_in_installed_scan_gate(self):
        scan_gate = (Path(__file__).parent / "scan-and-open.py").read_text()
        preferences = (Path(__file__).parent / "PDFMagicOpenerApp" /
                       "ScanProgressPreference.swift").read_text()
        self.assertNotIn("enhanced_embedded_files", scan_gate)
        self.assertNotIn("enhanced_embedded_files", preferences)
        self.assertIn("check_database()", scan_gate)
        self.assertIn("if not cached_clean(cache_id):", scan_gate)
        self.assertIn("remove_quarantine(path)", scan_gate)
        from protection_policy_definitions import (PROTECTION_POLICIES,
                                                   ProtectionProfileID)
        self.assertFalse(PROTECTION_POLICIES[ProtectionProfileID.ENHANCED].selectable)

    def test_absent_or_invalid_configuration_never_passes(self):
        self.pdf.write_bytes(sample_pdf(("x.txt", b"content")))
        for scanner in (None, "", False):
            with self.subTest(scanner=scanner):
                with self.assertRaises(inspector.EmbeddedFileInspectionError):
                    inspector.inspect_embedded_files(self.pdf, scanner, self.database)
        with self.assertRaises(ValueError):
            inspector.inspect_embedded_files(self.pdf, "/mock/clamscan",
                                             self.database, max_attachment_bytes=0)


if __name__ == "__main__":
    unittest.main()
