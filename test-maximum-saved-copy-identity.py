#!/usr/bin/env python3
"""opener-0547: generated copies must be distinguishable when offered for saving."""

from dataclasses import FrozenInstanceError, replace
from pathlib import Path
from unittest.mock import patch
import unittest

from maximum_sanitized_copy import (
    GENERATED_CONTENT_ORIGIN, SAVED_COPY_LABEL, SAVED_COPY_NOTICE,
    SanitizedCopyOffer, suggested_saved_copy_filename,
)


class SavedCopyIdentityTests(unittest.TestCase):
    def setUp(self):
        self.offer = SanitizedCopyOffer(b"%PDF-1.4\\nsynthetic generated PDF", 1)

    def test_suggested_name_is_distinct_from_original(self):
        for source, expected in (
            ("/Users/example/Quarterly Report.pdf", "Quarterly Report-sanitized-copy.pdf"),
            ("report.PDF", "report-sanitized-copy.pdf"),
            (Path("report.PDF"), "report-sanitized-copy.pdf"),
            ("report-sanitized-copy.pdf", "report-sanitized-copy-sanitized-copy.pdf"),
            ("Échéancier.pdf", "Échéancier-sanitized-copy.pdf"),
            ("...pdf", "document-sanitized-copy.pdf"),
            ("name:with?characters.pdf", "name-with-characters-sanitized-copy.pdf"),
            ("x" * 160 + ".pdf", "x" * 96 + "-sanitized-copy.pdf"),
        ):
            with self.subTest(source=source):
                suggested = suggested_saved_copy_filename(source)
                self.assertEqual(suggested, expected)
                self.assertNotEqual(suggested.casefold(), Path(source).name.casefold())
                self.assertEqual(Path(suggested).name, suggested)
                self.assertTrue(suggested.endswith("-sanitized-copy.pdf"))
                self.assertFalse(any(c in suggested for c in ("\\x00", "/", "\\n", "\\r")))
                self.assertEqual(suggested_saved_copy_filename(source), suggested)

    def test_reject_non_pdf_and_ambiguous_inputs(self):
        for source in ("", "readme.txt", ".pdf", "not-a-pdf", "bad\\x00name.pdf", None,
                       b"source.pdf"):
            with self.subTest(source=source), self.assertRaises(ValueError):
                suggested_saved_copy_filename(source)

    def test_save_presentation_distinguishes_generated_copy(self):
        public = self.offer.to_save_presentation("/private/secret source.pdf")
        self.assertEqual(public, {
            "contentOrigin": GENERATED_CONTENT_ORIGIN,
            "isUntouchedOriginal": False,
            "label": SAVED_COPY_LABEL,
            "notice": SAVED_COPY_NOTICE,
            "suggestedFilename": "secret source-sanitized-copy.pdf",
            "requiresFreshScan": True,
            "authorizesOpen": False,
        })
        self.assertIn("not the original", public["label"])
        self.assertIn("untouched original", public["notice"])
        self.assertNotIn("/private/", str(public))
        self.assertNotIn("secret source", self.offer.to_public_metadata()["explanation"])
        self.assertEqual(self.offer.pdf_bytes, b"%PDF-1.4\\nsynthetic generated PDF")

    def test_relabeling_or_removing_scan_gate_is_rejected(self):
        for change in (
            {"content_origin": "original"},
            {"content_origin": None},
            {"permits_open": True},
            {"needs_separate_scan": False},
            {"rasterized": False},
        ):
            with self.subTest(change=change), self.assertRaises(ValueError):
                replace(self.offer, **change)
        with self.assertRaises(FrozenInstanceError):
            self.offer.content_origin = "original"
        object.__setattr__(self.offer, "content_origin", "original")
        with self.assertRaises(ValueError):
            self.offer.to_save_presentation("source.pdf")

    def test_identity_contract_does_not_write_or_launch(self):
        with patch("builtins.open", side_effect=AssertionError("unexpected write")), \
                patch.object(Path, "write_bytes", side_effect=AssertionError("unexpected write")), \
                patch("os.open", side_effect=AssertionError("unexpected filesystem access")):
            self.offer.to_save_presentation("original.pdf")
        self.assertFalse(self.offer.permits_open)
        self.assertTrue(self.offer.needs_separate_scan)

    def test_ci_includes_identity_test_and_installed_scanner_stays_independent(self):
        root = Path(__file__).resolve().parent
        workflow = (root / ".github/workflows/consolidated-checks.yml").read_text(
            encoding="utf-8"
        )
        scanner = (root / "scan-and-open.py").read_text(encoding="utf-8")
        self.assertIn("python3 test-maximum-saved-copy-identity.py -v", workflow)
        self.assertNotIn("maximum_saved_copy_identity", scanner)


if __name__ == "__main__":
    unittest.main()
