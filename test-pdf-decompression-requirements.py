#!/usr/bin/env python3
"""Executable isolated Enhanced PDF decompression-budget regressions."""

import builtins
from dataclasses import FrozenInstanceError
from io import BytesIO
from pathlib import Path
import random
import unittest
from unittest.mock import patch
import zlib

from pypdf import PdfWriter
from pypdf.generic import DecodedStreamObject, NameObject

from pdf_decompression_requirements import (
    MAX_EXPANSION_RATIO,
    MAX_INPUT_BYTES,
    MAX_STREAM_DECODED_BYTES,
    MAX_TOTAL_DECODED_BYTES,
    PDFDecompressionInspection,
    PDFDecompressionInspectionError,
    inspect_pdf_decompression_requirements,
)


ROOT = Path(__file__).resolve().parent


def make_pdf(*streams):
    writer = PdfWriter()
    page = writer.add_blank_page(width=612, height=792)
    for payload, compressed in streams:
        stream = DecodedStreamObject()
        stream.set_data(payload)
        if compressed:
            stream = stream.flate_encode()
        reference = writer._add_object(stream)
        # The first stream is rendered as content; subsequent unattached
        # objects must still be checked through the xref object table.
        if "/Contents" not in page:
            page[NameObject("/Contents")] = reference
    output = BytesIO()
    writer.write(output)
    return output.getvalue()


def replace_stream_data(pdf, old, new):
    # Only deterministic test fixtures: the replacement must preserve the
    # /Length object for strict parser verification.
    assert len(old) == len(new)
    assert pdf.count(old) == 1
    return pdf.replace(old, new)


class PDFDecompressionRequirementsTests(unittest.TestCase):
    def test_uncompressed_and_regular_flate_streams_return_non_opening_metadata(self):
        contents = make_pdf((b"abcd" * 50, False), (bytes(range(256)) * 4, True))
        result = inspect_pdf_decompression_requirements(contents)
        self.assertEqual(result, PDFDecompressionInspection(2, 1, 1224, result.maximum_expansion_ratio))
        self.assertGreater(result.maximum_expansion_ratio, 1)
        self.assertFalse(result.permits_open)
        with self.assertRaises(FrozenInstanceError):
            result.stream_count = 99

    def test_blank_pdf_still_does_not_authorize_opening(self):
        self.assertEqual(inspect_pdf_decompression_requirements(make_pdf()),
                         PDFDecompressionInspection(0, 0, 0, 0))

    def test_high_ratio_bomb_is_blocked_before_full_inflation(self):
        data = make_pdf((b"A" * 2_000_000, True))
        with self.assertRaisesRegex(PDFDecompressionInspectionError, "exceed inspection limits"):
            inspect_pdf_decompression_requirements(data)

    def test_per_stream_cap_blocks_expansion_even_when_ratio_is_acceptable(self):
        # Deterministic incompressible data: the per-stream limit, not the
        # expansion-ratio limit, must independently reject this fixture.
        payload = random.Random(42).randbytes(MAX_STREAM_DECODED_BYTES + 1)
        pdf = make_pdf((payload, True))
        with self.assertRaises(PDFDecompressionInspectionError):
            inspect_pdf_decompression_requirements(pdf)

    def test_total_cap_counts_multiple_compressed_streams(self):
        payload = (random.Random(43).randbytes(128 * 1024) + b"A" * (7 * 1024 * 1024 - 128 * 1024))
        # Five individually bounded streams can exceed the aggregate cap
        # without exceeding the PDF input cap or per-stream expansion ratio.
        pdf = make_pdf(*[(payload, True) for _ in range(5)])
        with self.assertRaisesRegex(PDFDecompressionInspectionError, "exceed inspection limits"):
            inspect_pdf_decompression_requirements(pdf)

    def test_unreferenced_stream_objects_are_inspected(self):
        pdf = make_pdf((b"page data", False), (b"B" * 2_000_000, True))
        with self.assertRaises(PDFDecompressionInspectionError):
            inspect_pdf_decompression_requirements(pdf)

    def test_truncated_or_corrupt_deflate_and_trailing_members_are_refused(self):
        good = zlib.compress(b"payload" * 500)
        pdf = make_pdf((b"payload" * 500, True))
        self.assertIn(good, pdf)
        corrupted = replace_stream_data(pdf, good, bytes([good[0] ^ 0xff]) + good[1:])
        with self.assertRaises(PDFDecompressionInspectionError):
            inspect_pdf_decompression_requirements(corrupted)
        trailing = replace_stream_data(pdf, good, good[:-1] + b"x")
        with self.assertRaises(PDFDecompressionInspectionError):
            inspect_pdf_decompression_requirements(trailing)

    def test_unsupported_filters_and_malformed_pdf_fail_closed(self):
        good = make_pdf((b"abc", False))
        pdf = make_pdf((b"foo bar", True))
        self.assertIn(b"/FlateDecode", pdf)
        unsupported = pdf.replace(b"/FlateDecode", b"/DCTDecode  ")
        with self.assertRaises(PDFDecompressionInspectionError):
            inspect_pdf_decompression_requirements(unsupported)
        for malformed in (b"", b"hello", good[:-10], b"%PDF-1.4\n%%EOF", bytearray(good),
                          b"x" * (MAX_INPUT_BYTES + 1)):
            with self.subTest(case=type(malformed).__name__):
                with self.assertRaises(PDFDecompressionInspectionError):
                    inspect_pdf_decompression_requirements(malformed)

    def test_encrypted_input_is_not_decrypted(self):
        writer = PdfWriter()
        writer.add_blank_page(width=200, height=200)
        writer.encrypt("test-only-password")
        buffer = BytesIO()
        writer.write(buffer)
        with self.assertRaises(PDFDecompressionInspectionError) as issue:
            inspect_pdf_decompression_requirements(buffer.getvalue())
        self.assertNotIn("test-only-password", str(issue.exception))

    def test_dependency_missing_is_not_a_success(self):
        original = builtins.__import__

        def reject_pypdf(name, *args, **kwargs):
            if name == "pypdf" or name.startswith("pypdf."):
                raise ModuleNotFoundError("missing")
            return original(name, *args, **kwargs)

        with patch("builtins.__import__", side_effect=reject_pypdf):
            with self.assertRaisesRegex(PDFDecompressionInspectionError, "unavailable"):
                inspect_pdf_decompression_requirements(make_pdf())

    def test_no_active_scanner_integration_or_private_data_in_errors(self):
        module = (ROOT / "pdf_decompression_requirements.py").read_text(encoding="utf-8")
        scanner_path = ROOT / "scan-and-open.py"
        if scanner_path.exists():
            scanner = scanner_path.read_text(encoding="utf-8")
            self.assertNotIn("pdf_decompression_requirements", scanner)
            self.assertIn("verify_file_integrity", scanner)
            self.assertIn("if not cached_clean(cache_id):", scanner)
        for forbidden in ("get_data(", "subprocess.", "UserDefaults", "os.environ", "remove_quarantine(", "launch_clean_file("):
            self.assertNotIn(forbidden, module)
        workflow = ROOT / ".github/workflows/ci.yml"
        if workflow.exists():
            self.assertIn("python3 test-pdf-decompression-requirements.py -v", workflow.read_text(encoding="utf-8"))
        self.assertGreater(MAX_EXPANSION_RATIO, 1)
        self.assertGreater(MAX_TOTAL_DECODED_BYTES, MAX_STREAM_DECODED_BYTES)


if __name__ == "__main__":
    unittest.main()
