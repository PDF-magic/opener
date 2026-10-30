#!/usr/bin/env python3
"""Executable byte signatures in real generated PDFs, with no payload execution."""

from io import BytesIO
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

from pypdf import PdfWriter
from pypdf.generic import DecodedStreamObject, EncodedStreamObject, NameObject

import pdf_embedded_executable_content as inspector


def pdf_with_streams(*streams, indirect_only=False):
    writer = PdfWriter()
    writer.add_blank_page(width=200, height=200)
    for stream in streams:
        ref = writer._add_object(stream)
        if not indirect_only:
            writer.pages[0][NameObject("/Contents")] = ref
    output = BytesIO()
    writer.write(output)
    return output.getvalue()


def raw_stream(payload):
    stream = DecodedStreamObject()
    stream.set_data(payload)
    return stream


def flate_stream(payload):
    return raw_stream(payload).flate_encode()


def pe_bytes():
    stub = bytearray(128)
    stub[:2] = b"MZ"
    stub[60:64] = (80).to_bytes(4, "little")
    stub[80:84] = b"PE\0\0"
    return bytes(stub)


class EmbeddedExecutableInspectionTests(unittest.TestCase):
    def inspect(self, *streams, **kwargs):
        return inspector.inspect_pdf_embedded_executable_content(
            pdf_with_streams(*streams, **kwargs)
        )

    def test_regular_streams_and_empty_documents_provide_only_inert_evidence(self):
        empty = self.inspect()
        self.assertEqual((empty.inspected_stream_count, empty.executable_count), (0, 0))
        self.assertFalse(empty.permits_open)
        baseline = self.inspect(raw_stream(b"q 1 0 0 1 0 0 cm Q"))
        self.assertEqual((baseline.inspected_stream_count, baseline.executable_count), (1, 0))
        self.assertFalse(baseline.has_executables)

    def test_detects_pe_elf_macho_wasm_script_and_class_signatures(self):
        variants = ((pe_bytes(), "pe"), (b"\x7fELF\x02", "elf"),
                    (b"\xcf\xfa\xed\xfe" + b"z" * 8, "mach_o"),
                    (b"\0asm\x01\0\0\0", "wasm"),
                    (b"#!/usr/bin/env python3\nprint(1)", "script"),
                    (b"\xca\xfe\xba\xbe\0\0\0=", "java_or_fat_binary"),
                    (b"MZnot-full-pe", "dos_executable"))
        for payload, expected in variants:
            with self.subTest(kind=expected):
                outcome = self.inspect(raw_stream(payload))
                self.assertTrue(outcome.has_executables)
                self.assertEqual(outcome.executable_count, 1)
                self.assertEqual(outcome.executable_kinds, (expected,))

    def test_named_attachment_is_inspected_by_magic_not_extension(self):
        writer = PdfWriter()
        writer.add_blank_page(width=200, height=200)
        writer.add_attachment("ordinary.txt", pe_bytes())
        output = BytesIO()
        writer.write(output)
        result = inspector.inspect_pdf_embedded_executable_content(output.getvalue())
        self.assertTrue(result.has_executables)
        self.assertIn("pe", result.executable_kinds)

    def test_detects_orphan_indirect_stream_and_flate_payload(self):
        outcome = self.inspect(flate_stream(pe_bytes()), indirect_only=True)
        self.assertEqual(outcome.executable_kinds, ("pe",))
        self.assertEqual(outcome.inspected_stream_count, 1)

    def test_scans_multiple_streams_and_uses_deduplicated_safe_categories(self):
        outcome = self.inspect(raw_stream(b"\x7fELF"), raw_stream(b"\x7fELF"),
                               raw_stream(b"#! /bin/sh"), indirect_only=True)
        self.assertEqual((outcome.inspected_stream_count, outcome.executable_count), (3, 3))
        self.assertEqual(outcome.executable_kinds, ("elf", "script"))

    def test_data_is_not_inferred_executable_from_a_filename_or_keyword(self):
        outcome = self.inspect(raw_stream(b"ordinary prose says .exe ELF and javascript"))
        self.assertFalse(outcome.has_executables)

    def test_unsupported_filter_and_corrupt_stream_fail_closed(self):
        unsupported = raw_stream(b"opaque")
        unsupported[NameObject("/Filter")] = NameObject("/DCTDecode")
        with self.assertRaises(inspector.PDFEmbeddedExecutableInspectionError):
            self.inspect(unsupported)
        corrupted = EncodedStreamObject()
        corrupted._data = b"not a zlib stream"
        corrupted[NameObject("/Filter")] = NameObject("/FlateDecode")
        with self.assertRaises(inspector.PDFEmbeddedExecutableInspectionError):
            self.inspect(corrupted)

    def test_limits_missing_dependency_and_malformed_pdf_fail_closed(self):
        data = pdf_with_streams(raw_stream(b"x" * 400))
        with patch.object(inspector, "MAX_STREAM_BYTES", 100):
            with self.assertRaises(inspector.PDFEmbeddedExecutableInspectionError):
                inspector.inspect_pdf_embedded_executable_content(data)
        with patch.object(inspector, "MAX_TOTAL_STREAM_BYTES", 10):
            with self.assertRaises(inspector.PDFEmbeddedExecutableInspectionError):
                inspector.inspect_pdf_embedded_executable_content(data)
        for bad in (b"not a pdf", b"%PDF-1.4\n", b""):
            with self.subTest(data=bad):
                with self.assertRaises(inspector.PDFEmbeddedExecutableInspectionError):
                    inspector.inspect_pdf_embedded_executable_content(bad)
        with patch.dict(sys.modules, {"pypdf": None}):
            with self.assertRaises(inspector.PDFEmbeddedExecutableInspectionError):
                inspector.inspect_pdf_embedded_executable_content(data)
        writer = PdfWriter()
        writer.add_blank_page(width=200, height=200)
        writer.encrypt("password")
        out = BytesIO()
        writer.write(out)
        with self.assertRaises(inspector.PDFEmbeddedExecutableInspectionError):
            inspector.inspect_pdf_embedded_executable_content(out.getvalue())

    def test_metadata_cannot_be_used_to_authorize_open(self):
        with self.assertRaises(ValueError):
            inspector.PDFEmbeddedExecutableInspection(0, 0, (), permits_open=True)
        with self.assertRaises(ValueError):
            inspector.PDFEmbeddedExecutableInspection(0, 1, ("script",))
        with self.assertRaises(ValueError):
            inspector.PDFEmbeddedExecutableInspection(1, 1, ("user-payload",))

    def test_installed_scanner_and_preferences_remain_separate(self):
        original = Path(__file__).resolve().parents[2]
        scanner = original / "scan-and-open.py"
        if not scanner.exists():
            self.skipTest("Full repository unavailable in local fixture")
        deployed = scanner.read_text()
        self.assertNotIn("pdf_embedded_executable_content", deployed)
        self.assertIn("check_database()", deployed)
        self.assertIn("if not cached_clean(cache_id):", deployed)
        from protection_policy_definitions import PROTECTION_POLICIES, ProtectionProfileID
        self.assertFalse(PROTECTION_POLICIES[ProtectionProfileID.ENHANCED].selectable)


if __name__ == "__main__":
    unittest.main()
