#!/usr/bin/env python3
"""opener-0433: fail closed when PDF streams exceed decoded-byte budgets."""

from io import BytesIO
from pathlib import Path
from runpy import run_path
import unittest
from unittest.mock import patch

from pypdf import PdfWriter, get_configuration
from pypdf.generic import DecodedStreamObject

import pdf_structure_parser as parser


ROOT = Path(__file__).resolve().parent
LIMIT_MESSAGE = "The PDF exceeds the structure inspection limit; opening was stopped."


def compressed_pdf(*payloads):
    writer = PdfWriter()
    writer.add_blank_page(width=100, height=100)
    # Deliberately unreferenced objects must be inspected too.
    for payload in payloads:
        stream = DecodedStreamObject()
        stream.set_data(payload)
        writer._add_object(stream.flate_encode())
    output = BytesIO()
    writer.write(output)
    return output.getvalue()


class PDFDecodedSizeTests(unittest.TestCase):
    def test_exact_stream_limit_and_one_byte_over(self):
        with patch.object(parser, "MAX_STRUCTURE_DECOMPRESSED_STREAM_BYTES", 64), \
             patch.object(parser, "MAX_STRUCTURE_TOTAL_DECOMPRESSED_BYTES", 256):
            self.assertEqual(parser.parse_pdf_structure(compressed_pdf(b"A" * 64)).page_count, 1)
            with self.assertRaises(parser.PDFStructureParseError) as error:
                parser.parse_pdf_structure(compressed_pdf(b"A" * 65))
            self.assertEqual(str(error.exception), LIMIT_MESSAGE)

    def test_total_budget_is_inclusive_and_counts_unreferenced_streams(self):
        with patch.object(parser, "MAX_STRUCTURE_DECOMPRESSED_STREAM_BYTES", 64), \
             patch.object(parser, "MAX_STRUCTURE_TOTAL_DECOMPRESSED_BYTES", 128):
            self.assertEqual(
                parser.parse_pdf_structure(compressed_pdf(*([b"B" * 32] * 4))).page_count, 1
            )
            with self.assertRaises(parser.PDFStructureParseError) as error:
                parser.parse_pdf_structure(compressed_pdf(*([b"B" * 32] * 4), b"C"))
            self.assertEqual(str(error.exception), LIMIT_MESSAGE)

    def test_parser_configuration_is_restored_after_success_and_failure(self):
        initial = get_configuration()
        normal = compressed_pdf(b"safe")
        parser.parse_pdf_structure(normal)
        self.assertIs(get_configuration(), initial)
        with patch.object(parser, "MAX_STRUCTURE_DECOMPRESSED_STREAM_BYTES", 4):
            with self.assertRaises(parser.PDFStructureParseError):
                parser.parse_pdf_structure(compressed_pdf(b"longer"))
        self.assertIs(get_configuration(), initial)

    def test_xref_and_object_streams_are_bounded_before_implicit_decode(self):
        fixture = run_path(str(ROOT / "test-pdf-cross-reference-parsing.py"))["make_xref_stream_pdf"]
        document = fixture(object_stream=True, compressed_xref=True)
        self.assertEqual(parser.parse_pdf_structure(document).page_count, 1)
        # Implicit Flate decompression in PdfReader must use the same per-stream
        # ceiling, not an uncontrolled default that only applies after parsing.
        with patch.object(parser, "MAX_STRUCTURE_DECOMPRESSED_STREAM_BYTES", 8):
            with self.assertRaises(parser.PDFStructureParseError) as error:
                parser.parse_pdf_structure(document)
            # pypdf can normalize a decompression-limit exception raised
            # while reading an xref stream into a fixed structural failure.
            # Both are fail-closed, and neither grants an opening verdict.
            self.assertIn(str(error.exception), (
                LIMIT_MESSAGE,
                "PDF structure could not be verified; opening was stopped.",
            ))

    def test_unbounded_sized_streams_never_authorize_opening(self):
        document = compressed_pdf(b"PRIVATE_PAYLOAD" * 10)
        with patch.object(parser, "MAX_STRUCTURE_DECOMPRESSED_STREAM_BYTES", 32):
            with self.assertRaises(parser.PDFStructureParseError) as error:
                parser.parse_pdf_structure(document)
        self.assertNotIn("PRIVATE_PAYLOAD", str(error.exception))
        self.assertNotIn("authorizesOpen", str(error.exception))

    def test_budget_is_isolated_from_installed_scanner_and_ci_wired(self):
        scanner = (ROOT / "scan-and-open.py").read_text(encoding="utf-8")
        workflow = (ROOT / ".github/workflows/ci.yml").read_text(encoding="utf-8")
        self.assertNotIn("pdf_structure_parser", scanner)
        self.assertIn("verify_file_integrity", scanner)
        self.assertIn("python3 test-pdf-decompressed-size.py -v", workflow)
        self.assertEqual(parser.MAX_STRUCTURE_DECOMPRESSED_STREAM_BYTES, 8 * 1024 * 1024)
        self.assertEqual(parser.MAX_STRUCTURE_TOTAL_DECOMPRESSED_BYTES, 32 * 1024 * 1024)


if __name__ == "__main__":
    unittest.main()
