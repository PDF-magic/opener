#!/usr/bin/env python3
"""opener-0554: Save Sanitized PDF is explicit, verified and never a viewer action."""
from pathlib import Path
from types import SimpleNamespace
import tempfile
import unittest
from unittest.mock import patch

from maximum_sanitized_copy import (
    CONVERSION_CHANGE_WARNING, GENERATED_CONTENT_ORIGIN, SanitizedCopyOffer,
)
from scan_results import EFFECTIVE_POLICY_ID
import maximum_save_sanitized_pdf_action as action


class SaveSanitizedPDFInterfaceTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.folder = Path(tmp.name).resolve()
        self.destination = self.folder / "generated.pdf"
        self.offer = SanitizedCopyOffer(b"%PDF-1.4\nverified raster copy", 1)

    def verified(self):
        return patch("maximum_sanitized_copy._passive_pages", return_value=True)

    def test_fixed_action_metadata_only_for_verified_generated_content(self):
        self.assertIsNone(action.available_save_sanitized_pdf_action(self.offer))
        with self.verified():
            metadata = action.available_save_sanitized_pdf_action(self.offer)
        self.assertEqual(metadata, {
            "label": "Save Sanitized PDF",
            "contentOrigin": GENERATED_CONTENT_ORIGIN,
            "isUntouchedOriginal": False,
            "conversionWarning": CONVERSION_CHANGE_WARNING,
            "requiresExplicitAction": True,
            "requiresDestinationSelection": True,
            "requiresFreshScan": True,
            "authorizesOpen": False,
            "allowsOverwrite": False,
        })
        self.assertNotIn(str(self.destination), repr(metadata))
        for invalid in (None, self.offer.pdf_bytes, object()):
            with self.subTest(invalid=type(invalid).__name__):
                self.assertIsNone(action.available_save_sanitized_pdf_action(invalid))

    def test_decline_and_invalid_offer_never_show_destination_or_write(self):
        with self.verified(), patch.object(action, "save_sanitized_copy") as save:
            choices = []
            def chooser():
                choices.append(True)
                return self.destination
            for requested in (False, None, 1, "yes"):
                with self.subTest(requested=requested), self.assertRaises(
                    action.SaveSanitizedPDFActionError
                ):
                    action.save_sanitized_pdf_action(
                        self.offer, user_requested=requested, choose_destination=chooser)
            self.assertEqual(choices, [])
            save.assert_not_called()
        with patch.object(action, "save_sanitized_copy") as save:
            with self.assertRaises(action.SaveSanitizedPDFActionError):
                action.save_sanitized_pdf_action(
                    self.offer, user_requested=True, choose_destination=lambda: self.destination)
            save.assert_not_called()
        self.assertFalse(self.destination.exists())

    def test_click_asks_once_then_delegates_to_existing_fresh_scan_gate(self):
        choices = []
        def chooser():
            choices.append("presented")
            return self.destination
        with self.verified(), patch.object(
            action, "save_sanitized_copy", return_value=self.destination
        ) as backend:
            result = action.save_sanitized_pdf_action(
                self.offer, user_requested=True, choose_destination=chooser)
        self.assertEqual(result, self.destination)
        self.assertEqual(choices, ["presented"])
        backend.assert_called_once_with(
            self.offer, self.destination, user_confirmed=True)

    def test_cancel_does_not_stage_scan_or_write(self):
        with self.verified(), patch.object(action, "save_sanitized_copy") as backend:
            self.assertIsNone(action.save_sanitized_pdf_action(
                self.offer, user_requested=True, choose_destination=lambda: None))
            backend.assert_not_called()

    def test_destination_selection_errors_and_save_failures_are_path_free(self):
        def broken():
            raise OSError("/private/sensitive/source.pdf")
        with self.verified():
            with self.assertRaises(action.SaveSanitizedPDFActionError) as caught:
                action.save_sanitized_pdf_action(
                    self.offer, user_requested=True, choose_destination=broken)
            self.assertEqual(str(caught.exception), action.ACTION_BLOCKED_MESSAGE)
            with patch.object(action, "save_sanitized_copy",
                              side_effect=OSError("/private/secret output")):
                with self.assertRaises(action.SaveSanitizedPDFActionError) as caught:
                    action.save_sanitized_pdf_action(
                        self.offer, user_requested=True,
                        choose_destination=lambda: self.destination)
                self.assertEqual(str(caught.exception), action.ACTION_BLOCKED_MESSAGE)

    def test_real_exclusive_save_preserves_original_and_never_launches(self):
        original = self.folder / "untouched.pdf"
        original.write_bytes(b"%PDF-original must not change")
        def fresh_scan(staged_path, offer):
            self.assertEqual(Path(staged_path).read_bytes(), self.offer.pdf_bytes)
            self.assertIs(offer, self.offer)
            return SimpleNamespace(status="clean", from_cache=False,
                                   effective_policy_id=EFFECTIVE_POLICY_ID)
        with self.verified(), patch(
            "maximum_save_sanitized_copy._scan_staged_without_open",
            side_effect=fresh_scan
        ) as scan:
            result = action.save_sanitized_pdf_action(
                self.offer, user_requested=True,
                choose_destination=lambda: self.destination)
        self.assertEqual(result.read_bytes(), self.offer.pdf_bytes)
        self.assertEqual(original.read_bytes(), b"%PDF-original must not change")
        scan.assert_called_once()
        with self.verified(), patch(
            "maximum_save_sanitized_copy._scan_staged_without_open",
            side_effect=fresh_scan
        ):
            with self.assertRaises(action.SaveSanitizedPDFActionError):
                action.save_sanitized_pdf_action(
                    self.offer, user_requested=True,
                    choose_destination=lambda: self.destination)
        self.assertEqual(result.read_bytes(), self.offer.pdf_bytes)

    def test_preview_does_not_activate_maximum_or_open_original(self):
        from protection_profiles import PROTECTION_PROFILES, ProtectionProfileID
        self.assertFalse(PROTECTION_PROFILES[ProtectionProfileID.MAXIMUM].selectable)
        root = Path(__file__).resolve().parent
        source = (root / "maximum_save_sanitized_pdf_action.py").read_text()
        self.assertIn("return save_sanitized_copy(offer, destination, user_confirmed=True)", source)
        self.assertNotIn("launch_clean_file", source)
        self.assertNotIn("open_required_maximum_safe_copy", source)
        view = (root / "PDFMagicOpenerApp/ProtectionSettingsView.swift").read_text()
        self.assertIn('Button("Save Sanitized PDF")', view)
        self.assertIn("verifiedOfferAvailable: false", view)
        self.assertIn("onSaveRequested: nil", view)


if __name__ == "__main__":
    unittest.main()
