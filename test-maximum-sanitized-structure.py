#!/usr/bin/env python3
"""opener-0319: generated Maximum PDFs must have verifiable structure."""
from dataclasses import FrozenInstanceError
from io import BytesIO
from pathlib import Path
import subprocess
import sys
import unittest
from unittest.mock import patch
import zlib

from pypdf import PdfReader, PdfWriter
from pypdf.generic import (
    ArrayObject, ByteStringObject, DictionaryObject, NameObject, NumberObject,
    StreamObject,
)
import maximum_sanitized_copy as copies
from maximum_sanitized_structure import (
    BLOCK_MESSAGE, MAX_OUTPUT_BYTES, MAX_OUTPUT_PAGES,
    SanitizedPDFStructure, SanitizedPDFStructureError,
    verify_sanitized_pdf_structure,
)


def output_pdf(*, pages=1, compressed=False, info_metadata=False,
               catalog_metadata=False, page_metadata=False, file_id=False):
    writer = PdfWriter()
    # Valid generated-output fixtures model the sanitized writer's no-Info policy.
    writer._info = None
    for _ in range(pages):
        page = writer.add_blank_page(width=120, height=150)
        content = StreamObject()
        content._data = b"q 1 0 0 1 0 0 cm Q\n"
        if compressed:
            content._data = zlib.compress(content._data)
            content[NameObject("/Filter")] = NameObject("/FlateDecode")
        page[NameObject("/Contents")] = writer._add_object(content)
    if info_metadata:
        writer.add_metadata({"/Title": "PRIVATE-INFO-TITLE"})
    def metadata_stream():
        stream = StreamObject()
        stream._data = b"PRIVATE-XMP-METADATA"
        stream.update({
            NameObject("/Type"): NameObject("/Metadata"),
            NameObject("/Subtype"): NameObject("/XML"),
        })
        return stream
    if catalog_metadata:
        writer._root_object[NameObject("/Metadata")] = writer._add_object(metadata_stream())
    if page_metadata:
        writer.pages[0][NameObject("/Metadata")] = writer._add_object(metadata_stream())
    if file_id:
        writer._ID = ArrayObject([
            ByteStringObject(b"PRIVATE-DOCUMENT-ID"),
            ByteStringObject(b"PRIVATE-DOCUMENT-ID"),
        ])
    output = BytesIO()
    writer.write(output)
    return output.getvalue()


def corrupted(pdf, original, changed):
    assert original in pdf
    return pdf.replace(original, changed, 1)


class SanitizedStructureTests(unittest.TestCase):
    def test_valid_generated_pages_report_bounded_non_authorizing_evidence(self):
        for count in (1, 2, MAX_OUTPUT_PAGES):
            for compressed in (False, True):
                with self.subTest(count=count, compressed=compressed):
                    pdf = output_pdf(pages=count, compressed=compressed)
                    result = verify_sanitized_pdf_structure(pdf, count)
                    self.assertEqual(result.page_count, count)
                    self.assertGreater(result.object_count, 1)
                    self.assertIs(result.permits_open, False)
                    self.assertNotIn("pdf_bytes", vars(result))
                    with self.assertRaises(FrozenInstanceError):
                        result.permits_open = True

    def test_document_metadata_is_rejected_by_final_output_verifier(self):
        cases = (
            ("Info dictionary", output_pdf(info_metadata=True)),
            ("catalog XMP", output_pdf(catalog_metadata=True)),
            ("page XMP", output_pdf(page_metadata=True)),
            ("trailer file identifier", output_pdf(file_id=True)),
        )
        for label, candidate in cases:
            with self.subTest(metadata=label):
                with self.assertRaises(SanitizedPDFStructureError) as error:
                    verify_sanitized_pdf_structure(candidate, 1)
                self.assertEqual(str(error.exception), BLOCK_MESSAGE)

    def test_wrong_page_count_extra_pages_or_missing_pages_rejected(self):
        pdf = output_pdf(pages=2)
        for requested in (1, 3, True, 0, 17, "2"):
            with self.subTest(requested=requested):
                with self.assertRaises(SanitizedPDFStructureError):
                    verify_sanitized_pdf_structure(pdf, requested)

    def test_truncated_overlong_or_corrupt_framing_fails_closed(self):
        pdf = output_pdf()
        cases = (
            b"", "not bytes", bytearray(pdf), b"not a PDF",
            pdf[:-8], pdf + b"EXTRA-PAYLOAD",
            pdf.replace(b"startxref", b"startXREF", 1),
            pdf.replace(b"%PDF-", b"%PFX-", 1),
            b"X" * (MAX_OUTPUT_BYTES + 1),
        )
        for item in cases:
            with self.subTest(length=len(item)):
                with self.assertRaises(SanitizedPDFStructureError) as error:
                    verify_sanitized_pdf_structure(item, 1)
                self.assertEqual(str(error.exception), BLOCK_MESSAGE)

    def test_cross_reference_offset_and_missing_object_are_rejected(self):
        pdf = output_pdf()
        location = pdf.index(b"\nxref\n") + 1
        table = pdf[location:]
        lines = table.split(b"\n")
        entry = next(x for x in lines if x.startswith(b"000000") and x.endswith(b" n "))
        self.assertEqual(len(entry), 18 if entry.endswith(b" n") else 19)
        tampered = corrupted(pdf, entry, b"0000009999 00000 n ")
        for candidate in (tampered, corrupted(pdf, b"startxref\n",
                                               b"startxref\n999999999\n")):
            with self.assertRaises(SanitizedPDFStructureError):
                verify_sanitized_pdf_structure(candidate, 1)

    def test_page_tree_count_or_parent_conflicts_fail_closed(self):
        pdf = output_pdf()
        reader = PdfReader(BytesIO(pdf), strict=True)
        writer = PdfWriter()
        writer.add_blank_page(width=100, height=100)
        pages = writer._root_object["/Pages"]
        pages[NameObject("/Count")] = NumberObject(2)
        out = BytesIO()
        writer.write(out)
        for candidate in (out.getvalue(),
                          corrupted(pdf, b"/Type /Page", b"/Type /Xage")):
            with self.assertRaises(SanitizedPDFStructureError):
                verify_sanitized_pdf_structure(candidate, 1)

    def test_bad_compressed_page_content_is_not_accepted_as_valid_pdf(self):
        pdf = output_pdf(compressed=True)
        inflated = zlib.compress(b"q 1 0 0 1 0 0 cm Q\n")
        self.assertIn(inflated, pdf)
        # Corrupt one byte of the compressed stream without changing its length.
        changed = inflated[:3] + bytes([inflated[3] ^ 0xff]) + inflated[4:]
        bad = corrupted(pdf, inflated, changed)
        with self.assertRaises(SanitizedPDFStructureError):
            verify_sanitized_pdf_structure(bad, 1)

    def test_non_stream_contents_and_encrypted_output_are_rejected(self):
        writer = PdfWriter()
        page = writer.add_blank_page(width=100, height=100)
        page[NameObject("/Contents")] = ArrayObject([NumberObject(17)])
        data = BytesIO()
        writer.write(data)
        with self.assertRaises(SanitizedPDFStructureError):
            verify_sanitized_pdf_structure(data.getvalue(), 1)
        writer = PdfWriter()
        writer.add_blank_page(width=100, height=100)
        writer.encrypt("secret")
        data = BytesIO()
        writer.write(data)
        with self.assertRaises(SanitizedPDFStructureError):
            verify_sanitized_pdf_structure(data.getvalue(), 1)

    def test_generated_offer_must_pass_structure_after_passive_check(self):
        original = output_pdf(pages=1)
        converted = output_pdf(pages=2)
        with (patch.object(copies, "_trusted_converter", return_value=Path("/usr/bin/true")),
              patch.object(copies, "run_limited_converter", return_value=subprocess.CompletedProcess([], 0, converted)),
              patch.object(copies, "remove_active_pdf_functionality", return_value=converted),
              patch.object(copies, "_passive_pages", return_value=True),
              patch.object(copies, "verify_sanitized_pdf_structure",
                           side_effect=SanitizedPDFStructureError(BLOCK_MESSAGE)) as verify):
            self.assertIsNone(copies.offer_sanitized_pdf_copy(original))
            verify.assert_called_once()
        with (patch.object(copies, "_trusted_converter", return_value=Path("/usr/bin/true")),
              patch.object(copies, "run_limited_converter", return_value=subprocess.CompletedProcess([], 0, converted)),
              patch.object(copies, "remove_active_pdf_functionality", return_value=converted),
              patch.object(copies, "_passive_pages", return_value=True),
              patch.object(copies, "verify_sanitized_pdf_structure",
                           return_value=SanitizedPDFStructure(1, 5))):
            offer = copies.offer_sanitized_pdf_copy(original)
            self.assertIsNotNone(offer)
            self.assertTrue(offer.needs_separate_scan)
            self.assertFalse(offer.permits_open)

    def test_immutable_evidence_and_scanner_configuration_remain_unchanged(self):
        with self.assertRaises(ValueError):
            SanitizedPDFStructure(1, 1, permits_open=True)
        root = Path(__file__).resolve().parent
        scanner = (root / "scan-and-open.py").read_text()
        self.assertNotIn("maximum_sanitized_structure", scanner)
        self.assertIn("if not cached_clean(cache_id):", scanner)
        from protection_profiles import PROTECTION_PROFILES, ProtectionProfileID
        self.assertFalse(PROTECTION_PROFILES[ProtectionProfileID.MAXIMUM].selectable)


@unittest.skipUnless(sys.platform == "darwin", "Native raster converter requires macOS")
class NativeStructureTests(unittest.TestCase):
    def test_real_rasterized_pdf_passes_independent_structural_validation(self):
        pdf = output_pdf(pages=2)
        offer = copies.offer_sanitized_pdf_copy(pdf)
        self.assertIsNotNone(offer)
        report = verify_sanitized_pdf_structure(offer.pdf_bytes, 2)
        self.assertEqual(report.page_count, 2)
        self.assertFalse(report.permits_open)
        self.assertFalse(offer.permits_open)


if __name__ == "__main__":
    unittest.main()
