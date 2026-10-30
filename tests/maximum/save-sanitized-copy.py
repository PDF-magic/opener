#!/usr/bin/env python3
"""opener-0544: opt-in sanitized-copy save must never bypass fresh scanning."""
from pathlib import Path
from types import SimpleNamespace
import tempfile
import unittest
from unittest.mock import patch

from maximum_sanitized_copy import SanitizedCopyOffer
from scan_results import EFFECTIVE_POLICY_ID
import maximum_save_sanitized_copy as saving


class SaveSanitizedCopyTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.directory = Path(temporary.name).resolve()
        self.destination = self.directory / "saved.pdf"
        self.source = self.directory / "original.pdf"
        self.source.write_bytes(b"%PDF-original must remain untouched")
        self.offer = SanitizedCopyOffer(b"%PDF-generated content fixture", 1)
        passive = patch("maximum_sanitized_copy._passive_pages", return_value=True)
        passive.start()
        self.addCleanup(passive.stop)

    def clean(self, path, offer):
        self.assertNotEqual(Path(path), self.source)
        self.assertNotEqual(Path(path), self.destination)
        self.assertEqual(Path(path).read_bytes(), self.offer.pdf_bytes)
        self.assertEqual(offer, self.offer)
        return SimpleNamespace(status="clean", from_cache=False,
                               effective_policy_id=EFFECTIVE_POLICY_ID)

    def test_successful_explicit_save_is_private_and_never_opens_original(self):
        staged = []
        def scan(path, offer):
            staged.append(Path(path))
            return self.clean(path, offer)
        with patch.object(saving, "_scan_staged_without_open", side_effect=scan) as gate:
            saved = saving.save_sanitized_copy(
                self.offer, self.destination, user_confirmed=True)
        gate.assert_called_once()
        self.assertEqual(saved, self.destination)
        self.assertEqual(saved.read_bytes(), self.offer.pdf_bytes)
        self.assertEqual(saved.stat().st_mode & 0o777, 0o600)
        self.assertFalse(staged[0].exists())
        self.assertFalse(staged[0].parent.exists())
        self.assertEqual(self.source.read_bytes(), b"%PDF-original must remain untouched")

    def test_no_explicit_opt_in_creates_no_files_or_scan(self):
        with patch.object(saving, "_scan_staged_without_open") as gate:
            for consent in (False, None, 0, "yes"):
                with self.subTest(consent=consent), \
                        self.assertRaises(saving.SanitizedCopySaveError):
                    saving.save_sanitized_copy(
                        self.offer, self.destination, user_confirmed=consent)
        gate.assert_not_called()
        self.assertFalse(self.destination.exists())

    def test_only_a_verified_generated_offer_can_be_saved(self):
        with patch.object(saving, "_scan_staged_without_open") as gate:
            for offer in (None, b"%PDF-original", "generated"):
                with self.subTest(offer=offer), \
                        self.assertRaises(saving.SanitizedCopySaveError):
                    saving.save_sanitized_copy(
                        offer, self.destination, user_confirmed=True)
            gate.assert_not_called()
        self.assertFalse(self.destination.exists())

    def test_existing_target_or_symlink_cannot_be_overwritten(self):
        for symlink in (False, True):
            target = self.directory / "protected.pdf"
            target.write_bytes(b"preserve the user's file")
            if symlink:
                self.destination.symlink_to(target)
            else:
                self.destination.write_bytes(b"preserve the user's file")
            with patch.object(saving, "_scan_staged_without_open",
                              side_effect=self.clean):
                with self.assertRaises(saving.SanitizedCopySaveError):
                    saving.save_sanitized_copy(
                        self.offer, self.destination, user_confirmed=True)
            self.assertEqual(target.read_bytes(), b"preserve the user's file")
            if not symlink:
                self.assertEqual(self.destination.read_bytes(),
                                 b"preserve the user's file")
            self.destination.unlink()

    def test_reject_unsafe_destination_before_scanning(self):
        bad = ("relative.pdf", self.directory / "bad.txt",
               self.directory / "missing" / "new.pdf",
               str(self.directory / "bad.pdf") + "\x00")
        with patch.object(saving, "_scan_staged_without_open") as gate:
            for destination in bad:
                with self.subTest(destination=repr(destination)), \
                        self.assertRaises(saving.SanitizedCopySaveError):
                    saving.save_sanitized_copy(
                        self.offer, destination, user_confirmed=True)
        # The missing directory failure reaches scanning, but never creates output.
        self.assertFalse((self.directory / "missing").exists())
        self.assertFalse(self.destination.exists())

    def test_failed_incomplete_and_cached_scan_never_save(self):
        for outcome in (
            None,
            SimpleNamespace(status="infected", effective_policy_id=EFFECTIVE_POLICY_ID,
                            from_cache=False),
            SimpleNamespace(status="clean", effective_policy_id=EFFECTIVE_POLICY_ID,
                            from_cache=True),
            SimpleNamespace(status="clean", effective_policy_id="maximum",
                            from_cache=False),
            RuntimeError("private temporary path"),
        ):
            with self.subTest(outcome=type(outcome).__name__):
                def scan(path, offer):
                    if isinstance(outcome, Exception):
                        raise outcome
                    return outcome
                with patch.object(saving, "_scan_staged_without_open", side_effect=scan), \
                        self.assertRaises(saving.SanitizedCopySaveError) as captured:
                    saving.save_sanitized_copy(
                        self.offer, self.destination, user_confirmed=True)
                self.assertEqual(str(captured.exception), saving.SAVE_BLOCKED_MESSAGE)
                self.assertFalse(self.destination.exists())

    def test_installed_maximum_profile_remains_unselectable(self):
        from protection_profiles import PROTECTION_PROFILES, ProtectionProfileID
        self.assertFalse(PROTECTION_PROFILES[ProtectionProfileID.MAXIMUM].selectable)
        scanner = Path(__file__).with_name("scan-and-open.py").read_text()
        self.assertIn("force_rescan=True, expected_fingerprint=expected, scan_only=True",
                      scanner)
        self.assertIn("if scan_only:", scanner)


if __name__ == "__main__":
    unittest.main()
