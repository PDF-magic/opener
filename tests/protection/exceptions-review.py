#!/usr/bin/env python3
"""opener-0349: review unsupported exceptions without creating a bypass."""

from dataclasses import FrozenInstanceError
from pathlib import Path
import unittest

from protection_exception_policy import (
    EXCEPTION_SUPPORT_DECISION,
    ExceptionDisposition,
    ProtectionExceptionNotSupported,
    request_protection_exception,
)

ROOT = Path(__file__).resolve().parent
VIEW = (ROOT / "PDFMagicOpenerApp/ProtectionSettingsView.swift").read_text(
    encoding="utf-8"
)
CI = (ROOT / ".github/workflows/ci.yml").read_text(encoding="utf-8")


class ProtectionExceptionReviewTests(unittest.TestCase):
    def test_review_is_accessible_and_displays_an_explicit_empty_state(self):
        self.assertIn('GroupBox("Protection exceptions")', VIEW)
        section = VIEW.split('GroupBox("Protection exceptions")', 1)[1].split(
            'GroupBox("Malware scanning")', 1
        )[0]
        for expected in (
            "DisclosureGroup(isExpanded: $showExistingExceptions)",
            'Text("Review existing exceptions (0)")',
            'Text("Existing exceptions: none")',
            'accessibilityIdentifier("reviewExistingProtectionExceptions")',
            'accessibilityIdentifier("existingProtectionExceptionsEmpty")',
            "There are no approved files, folders, download sources",
            "Rejected exception requests are not saved as exceptions.",
            "This does not change scanning or settings.",
        ):
            with self.subTest(expected=expected):
                self.assertIn(expected, section)

    def test_review_is_read_only_and_does_not_store_or_approve_exceptions(self):
        self.assertIn("@State private var showExistingExceptions = false", VIEW)
        section = VIEW.split('GroupBox("Protection exceptions")', 1)[1].split(
            'GroupBox("Malware scanning")', 1
        )[0]
        for forbidden in (
            "Button(", "Toggle(", "Picker(", "TextField(", "SecureField(",
            "@AppStorage", "UserDefaults", "NSWorkspace", "Process(",
            "onTapGesture", "saveExplicitChoice", "request_protection_exception",
            "FileManager", "onChange(", "onSubmit(",
        ):
            with self.subTest(forbidden=forbidden):
                self.assertNotIn(forbidden, section)
        self.assertFalse(EXCEPTION_SUPPORT_DECISION.supported)
        self.assertIs(EXCEPTION_SUPPORT_DECISION.disposition,
                      ExceptionDisposition.UNSUPPORTED)
        self.assertEqual(EXCEPTION_SUPPORT_DECISION.as_document()["disposition"],
                         "unsupported")
        with self.assertRaises(FrozenInstanceError):
            EXCEPTION_SUPPORT_DECISION.supported = True
        for attempted in (None, {"file": "private.pdf", "approved": True},
                          {"path": "/private/example.pdf", "bypass": True}):
            with self.subTest(attempted=type(attempted).__name__):
                with self.assertRaises(ProtectionExceptionNotSupported):
                    request_protection_exception(attempted)

    def test_scan_and_preferences_are_not_connected_to_review_presentation(self):
        scanner = (ROOT / "scan-and-open.py").read_text(encoding="utf-8")
        self.assertIn("if not cached_clean(cache_id):", scanner)
        self.assertIn("decision = decide_opening(detection)", scanner)
        self.assertIn("verify_file_integrity(path, before, identity)", scanner)
        self.assertNotIn("showExistingExceptions", scanner)
        self.assertNotIn("reviewExistingProtectionExceptions", scanner)
        self.assertIn("python3 test-protection-exceptions-review.py -v", CI)
        self.assertIn("macos-build:", CI)


if __name__ == "__main__":
    unittest.main()
