#!/usr/bin/env python3
"""opener-0293: malformed structural syntax must fail closed."""
import builtins
from dataclasses import FrozenInstanceError
from io import BytesIO
from pathlib import Path
import re
import unittest
from unittest.mock import patch

from pypdf import PdfWriter
from pdf_malformed_structures import (
    BLOCK_MESSAGE, MAX_PDF_BYTES, PDFMalformedStructureError,
    PDFMalformedStructureInspection, inspect_pdf_malformed_structures,
)


def sample_pdf(pages=1):
    writer = PdfWriter()
    for _ in range(pages):
        writer.add_blank_page(width=612, height=792)
    buffer = BytesIO()
    writer.write(buffer)
    return buffer.getvalue()


class MalformedStructureTests(unittest.TestCase):
    def assert_rejected(self, data):
        with self.assertRaises(PDFMalformedStructureError) as error:
            inspect_pdf_malformed_structures(data)
        self.assertEqual(str(error.exception), BLOCK_MESSAGE)

    def test_generated_real_pdf_and_immutable_evidence(self):
        contents = sample_pdf(pages=2)
        result = inspect_pdf_malformed_structures(contents)
        self.assertIsInstance(result, PDFMalformedStructureInspection)
        self.assertEqual(result.page_count, 2)
        self.assertGreaterEqual(result.object_count, 5)
        self.assertFalse(result.malformed)
        self.assertFalse(result.permits_open)
        with self.assertRaises(FrozenInstanceError):
            result.permits_open = True
        with self.assertRaises(ValueError):
            PDFMalformedStructureInspection(1, 1, permits_open=True)

    def test_reference_pdf_collection(self):
        from reference_pdf_collection import REFERENCE_PDFS
        for sample in REFERENCE_PDFS:
            with self.subTest(sample=sample.identifier):
                before = sample.content
                report = inspect_pdf_malformed_structures(before)
                self.assertEqual(report.page_count, 1)
                self.assertIs(sample.content, before)

    def test_missing_header_eof_and_invalid_input_fail_closed(self):
        contents = sample_pdf()
        samples = [b"", b"not pdf", b"%PDF-1.4\n", b"%PDF-1.4\n%%EOF\n",
                   contents[:-10], contents + b"trailing private content",
                   contents.replace(b"%PDF-1.3", b"%PDF-9.9", 1),
                   bytearray(contents), memoryview(contents), None, True]
        for value in samples:
            with self.subTest(type=type(value).__name__):
                self.assert_rejected(value)

    def test_cross_reference_offset_must_identify_actual_object(self):
        contents = sample_pdf()
        offset = re.search(rb"(?m)^([0-9]{10}) 00000 n ", contents)
        self.assertIsNotNone(offset)
        corrupt = (contents[:offset.start(1)] + b"9999999999"
                   + contents[offset.end(1):])
        self.assert_rejected(corrupt)

    def test_cross_reference_header_generation_must_match(self):
        contents = sample_pdf()
        header = re.search(rb"(?m)^(\d+) (0) obj", contents)
        self.assertIsNotNone(header)
        corrupt = (contents[:header.start(2)] + b"1"
                   + contents[header.end(2):])
        self.assert_rejected(corrupt)

    def test_invalid_startxref_and_trailer_size(self):
        contents = sample_pdf()
        start = re.search(rb"startxref\s+(\d+)", contents)
        size = re.search(rb"/Size\s+(\d+)", contents)
        self.assertIsNotNone(start)
        self.assertIsNotNone(size)
        self.assert_rejected(contents[:start.start(1)] + b"9999999999" + contents[start.end(1):])
        self.assert_rejected(contents[:size.start(1)] + b"2" + contents[size.end(1):])

    def test_invalid_catalog_and_page_tree(self):
        contents = sample_pdf()
        self.assert_rejected(contents.replace(b"/Catalog", b"/Invalid", 1))
        self.assertRegex(contents, rb"/Pages\s+\d+\s+\d+\s+R")
        self.assert_rejected(re.sub(rb"/Pages(?=\s+\d+\s+\d+\s+R)",
                                    b"/Other", contents, count=1))

    def test_encrypted_is_not_decrypted(self):
        writer = PdfWriter()
        writer.add_blank_page(width=612, height=792)
        writer.encrypt("fixture-only-password")
        output = BytesIO()
        writer.write(output)
        self.assert_rejected(output.getvalue())

    def test_input_and_object_budget_fail_closed(self):
        self.assert_rejected(b"x" * (MAX_PDF_BYTES + 1))
        with patch("pdf_malformed_structures.MAX_OBJECTS", 1):
            self.assert_rejected(sample_pdf())

    def test_missing_library_is_not_silently_accepted(self):
        original = builtins.__import__
        def block(name, *args, **kwargs):
            if name == "pypdf":
                raise ModuleNotFoundError("not installed")
            return original(name, *args, **kwargs)
        with patch("builtins.__import__", side_effect=block):
            self.assert_rejected(sample_pdf())

    def test_scanner_and_user_customizations_are_unchanged(self):
        root = Path(__file__).resolve().parent
        scanner = (root / "scan-and-open.py").read_text(encoding="utf-8")
        self.assertNotIn("pdf_malformed_structures", scanner)
        self.assertIn("if not cached_clean(cache_id):", scanner)
        self.assertIn("verify_file_integrity", scanner)
        from protection_policy_definitions import PROTECTION_POLICIES, ProtectionProfileID
        self.assertFalse(PROTECTION_POLICIES[ProtectionProfileID.ENHANCED].selectable)


if __name__ == "__main__":
    unittest.main()
