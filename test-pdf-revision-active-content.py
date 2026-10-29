#!/usr/bin/env python3
"""opener-0450: detect replaced historical active objects without execution."""
from dataclasses import FrozenInstanceError
from pathlib import Path
import os
import socket
import subprocess
import unittest
from unittest.mock import patch

from pdf_revision_active_content import (
    BLOCK_MESSAGE, PDFHistoricalActiveContent,
    PDFHistoricalActiveContentError, inspect_pdf_revision_active_content,
)
from reference_pdf_collection import REFERENCE_PDFS


ROOT = Path(__file__).resolve().parent


def append_revision(original, number, data):
    previous = original.rsplit(b"startxref\n", 1)[1].splitlines()[0]
    updated = bytearray(original)
    at = len(updated)
    updated.extend(str(number).encode() + b" 0 obj\n" + data + b"\nendobj\n")
    xref = len(updated)
    # A zero-indexed free entry avoids library xref offset correction.\n    updated.extend(b"xref\n0 1\n0000000000 65535 f \n")\n    updated.extend(str(number).encode() + b" 1\n")
    updated.extend(f"{at:010d} 00000 n \n".encode())
    updated.extend(b"trailer\n<< /Size 12 /Root 1 0 R /Prev " + previous + b" >>\n")
    updated.extend(b"startxref\n" + str(xref).encode() + b"\n%%EOF\n")
    return bytes(updated)


class PDFHistoricalActiveTests(unittest.TestCase):
    def setUp(self):
        self.original = REFERENCE_PDFS[0].content

    def test_reference_collection_has_no_historical_active_content(self):
        for item in REFERENCE_PDFS:
            with self.subTest(name=item.identifier):
                record = inspect_pdf_revision_active_content(item.content)
                self.assertEqual(record.revision_count, 1)
                self.assertEqual(record.historical_active_object_count, 0)
                self.assertFalse(record.has_hidden_active_content)
                self.assertFalse(record.permits_open)

    def test_javascript_replaced_in_incremental_revision_is_detected(self):
        old = append_revision(self.original, 6, b"<< /S /JavaScript /JS (secret-data) >>")
        current = append_revision(old, 6, b"<< /Marker (now inert) >>")
        with (patch.object(socket, "getaddrinfo") as dns,
              patch.object(os, "system") as shell,
              patch.object(subprocess, "run") as process):
            import sys
            failures = []
            def trace(frame, event, argument):
                if (event == "exception" and frame.f_code.co_name in
                        ("inspect_pdf_incremental_revisions", "_read_xref")):
                    failures.append((frame.f_code.co_name, frame.f_lineno,
                                     type(argument[1]).__name__, str(argument[1])[:180]))
                return trace
            sys.settrace(trace)
            try:
                record = inspect_pdf_revision_active_content(current)
            except Exception:
                self.fail("Synthetic fixture trace: " + repr(failures[-12:]))
            finally:
                sys.settrace(None)
        self.assertEqual(record.revision_count, 3)
        self.assertEqual(record.historical_active_object_count, 1)
        self.assertEqual(record.hidden_active_object_count, 1)
        self.assertEqual(record.hidden_categories, ("javascript",))
        self.assertTrue(record.has_hidden_active_content)
        self.assertFalse(record.permits_open)
        self.assertNotIn("secret-data", repr(record))
        dns.assert_not_called()
        shell.assert_not_called()
        process.assert_not_called()
        with self.assertRaises(FrozenInstanceError):
            record.permits_open = True

    def test_retained_historical_action_is_not_mislabeled_hidden(self):
        old = append_revision(self.original, 6, b"<< /S /URI /URI (https://private.invalid) >>")
        current = append_revision(old, 7, b"<< /Marker (later) >>")
        record = inspect_pdf_revision_active_content(current)
        self.assertEqual(record.revision_count, 3)
        self.assertEqual(record.historical_active_object_count, 1)
        self.assertEqual(record.hidden_active_object_count, 0)
        self.assertEqual(record.hidden_categories, ())

    def test_orphaned_multimedia_and_attachment_objects_are_detected(self):
        old = append_revision(self.original, 7,
                              b"<< /Subtype /RichMedia /RichMediaContent << /Assets <<>> >> "
                              b"/AF [<< /EF << /F 9 0 R >> >>] >>")
        current = append_revision(old, 7, b"<< /Type /Ordinary >>")
        report = inspect_pdf_revision_active_content(current)
        self.assertEqual(report.hidden_categories, ("attachment", "multimedia"))
        self.assertEqual(report.hidden_active_object_count, 1)

    def test_nested_automatic_form_actions_detected_without_script_decoding(self):
        old = append_revision(self.original, 6,
                              b"<< /AA << /O << /S /SubmitForm /F (private) >> >> >>")
        current = append_revision(old, 6, b"<< /Marker /Safe >>")
        report = inspect_pdf_revision_active_content(current)
        self.assertEqual(report.hidden_categories, ("automatic_action", "form_action"))

    def test_literal_text_does_not_count_as_active_pdf_objects(self):
        old = append_revision(self.original, 6,
                              b"<< /Title (/S /JavaScript /JS (this is text)) >>")
        current = append_revision(old, 6, b"<< /Marker /Safe >>")
        report = inspect_pdf_revision_active_content(current)
        self.assertFalse(report.has_hidden_active_content)

    def test_invalid_and_tampered_revision_chains_fail_closed(self):
        once = append_revision(self.original, 6, b"<< /S /Launch /F (safe) >>")
        prev = self.original.rsplit(b"startxref\n", 1)[1].splitlines()[0]
        for data in (b"", "not bytes", b"bad", once[:-7],
                     once.replace(b"/Prev " + prev, b"/Prev 999999")):
            with self.subTest(data_type=type(data).__name__):
                with self.assertRaises(PDFHistoricalActiveContentError) as failure:
                    inspect_pdf_revision_active_content(data)
                self.assertEqual(str(failure.exception), BLOCK_MESSAGE)

    def test_resource_limits_and_metadata_validation(self):
        old = append_revision(self.original, 6, b"<< /S /JavaScript /JS (secret) >>")
        current = append_revision(old, 6, b"<< /Marker /Safe >>")
        import pdf_revision_active_content as stage
        with patch.object(stage, "MAX_REVISIONS", 2):
            with self.assertRaises(PDFHistoricalActiveContentError):
                inspect_pdf_revision_active_content(current)
        with patch.object(stage, "MAX_OBJECTS", 1):
            with self.assertRaises(PDFHistoricalActiveContentError):
                inspect_pdf_revision_active_content(current)
        for bad in (-1, True, 513):
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                PDFHistoricalActiveContent(1, 0, bad, ("javascript",))
        with self.assertRaises(ValueError):
            PDFHistoricalActiveContent(2, 1, 1, ("untrusted-secret",))

    def test_ci_and_installed_scan_gate_are_unchanged(self):
        ci = (ROOT / ".github/workflows/ci.yml").read_text(encoding="utf-8")
        self.assertIn("python3 test-pdf-revision-active-content.py -v", ci)
        scanner = (ROOT / "scan-and-open.py").read_text(encoding="utf-8")
        self.assertNotIn("pdf_revision_active_content", scanner)
        self.assertIn("if not cached_clean(cache_id):", scanner)
        from protection_policy_definitions import PROTECTION_POLICIES, ProtectionProfileID
        self.assertFalse(PROTECTION_POLICIES[ProtectionProfileID.ENHANCED].selectable)


if __name__ == "__main__":
    unittest.main()
