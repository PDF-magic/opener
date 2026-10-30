#!/usr/bin/env python3
"""opener-0553: view only a verified, freshly scanned generated PDF on request."""
from pathlib import Path
from types import SimpleNamespace
import stat
import unittest
from unittest.mock import patch

from maximum_sanitized_copy import (
    CONVERSION_CHANGE_WARNING, GENERATED_CONTENT_ORIGIN, SanitizedCopyOffer,
)
from scan_results import EFFECTIVE_POLICY_ID
import maximum_view_sanitized_pdf as view


class SanitizedPDFViewTests(unittest.TestCase):
    def setUp(self):
        self.offer = SanitizedCopyOffer(b"%PDF-1.4\\nsynthetic generated copy", 1)

    def clean(self):
        return SimpleNamespace(status="clean", effective_policy_id=EFFECTIVE_POLICY_ID,
                               from_cache=False)

    def test_action_available_only_after_strict_generated_copy_validation(self):
        self.assertIsNone(view.available_view_sanitized_pdf_action(self.offer))
        with patch("maximum_sanitized_copy._passive_pages", return_value=True):
            metadata = view.available_view_sanitized_pdf_action(self.offer)
        self.assertEqual(metadata["label"], "View Sanitized PDF")
        self.assertEqual(metadata["contentOrigin"], GENERATED_CONTENT_ORIGIN)
        self.assertFalse(metadata["isUntouchedOriginal"])
        self.assertEqual(metadata["conversionWarning"], CONVERSION_CHANGE_WARNING)
        self.assertFalse(metadata["authorizesOpen"])
        self.assertTrue(metadata["requiresExplicitAction"])
        self.assertTrue(metadata["requiresFreshScan"])
        for invalid in (None, self.offer.pdf_bytes, object()):
            with self.subTest(invalid=type(invalid).__name__):
                self.assertIsNone(view.available_view_sanitized_pdf_action(invalid))
        for key, value in (("content_origin", "original"), ("needs_separate_scan", False)):
            forged = SanitizedCopyOffer(self.offer.pdf_bytes, 1)
            object.__setattr__(forged, key, value)
            self.assertIsNone(view.available_view_sanitized_pdf_action(forged))

    def test_declining_never_stages_scans_or_launches(self):
        with patch("maximum_sanitized_copy._passive_pages", return_value=True), \
                patch.object(view, "stage_maximum_temporary_pdf") as stage, \
                patch.object(view, "_scan_staged_copy") as scan:
            for decision in (False, None, 1, "yes"):
                with self.subTest(decision=decision), \
                        self.assertRaises(view.SanitizedPDFViewError):
                    view.view_sanitized_pdf(self.offer, user_requested=decision)
            stage.assert_not_called()
            scan.assert_not_called()

    def test_explicit_view_scans_exact_private_generated_bytes_and_keeps_lease(self):
        visited = []
        def scan(path, offer):
            path = Path(path)
            visited.append((path, path.read_bytes(), offer))
            self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o600)
            self.assertEqual(stat.S_IMODE(path.parent.stat().st_mode), 0o700)
            self.assertRegex(path.name, r"^safe-copy-[0-9a-f]{32}\.pdf$")
            return self.clean()

        with patch("maximum_sanitized_copy._passive_pages", return_value=True), \
                patch.object(view, "_scan_staged_copy", side_effect=scan):
            session = view.view_sanitized_pdf(self.offer, user_requested=True)
        self.addCleanup(session.release_after_viewer_closes)
        self.assertEqual(len(visited), 1)
        path, bytes_seen, offered = visited[0]
        self.assertIs(offered, self.offer)
        self.assertEqual(bytes_seen, self.offer.pdf_bytes)
        self.assertEqual(session.copy_path, path)
        self.assertTrue(path.exists(), "Must not remove file while viewer needs it")
        public = session.to_public_metadata()
        self.assertTrue(public["freshlyScanned"])
        self.assertFalse(public["originalOpened"])
        self.assertFalse(public["isUntouchedOriginal"])
        self.assertNotIn(str(path), str(public))
        session.release_after_viewer_closes()
        session.release_after_viewer_closes()
        self.assertFalse(path.exists())

    def test_failed_scan_and_nonfresh_or_wrong_policy_never_return_session(self):
        responses = (
            RuntimeError("/private/secret source.pdf"),
            SimpleNamespace(status="infected", effective_policy_id=EFFECTIVE_POLICY_ID,
                            from_cache=False),
            SimpleNamespace(status="clean", effective_policy_id="Maximum", from_cache=False),
            SimpleNamespace(status="clean", effective_policy_id=EFFECTIVE_POLICY_ID,
                            from_cache=True),
            None,
        )
        for result in responses:
            paths = []
            def attempt(path, offer):
                paths.append(Path(path))
                if isinstance(result, Exception):
                    raise result
                return result
            with self.subTest(result=type(result).__name__), \
                    patch("maximum_sanitized_copy._passive_pages", return_value=True), \
                    patch.object(view, "_scan_staged_copy", side_effect=attempt), \
                    self.assertRaisesRegex(view.SanitizedPDFViewError,
                                            "^The sanitized PDF could not be viewed safely\\.$") as caught:
                view.view_sanitized_pdf(self.offer, user_requested=True)
            self.assertEqual(len(paths), 1)
            self.assertFalse(paths[0].exists())
            self.assertNotIn("secret", str(caught.exception))

    def test_unverified_or_forged_offers_cannot_stage_or_open(self):
        with patch.object(view, "stage_maximum_temporary_pdf") as stage, \
                patch.object(view, "_scan_staged_copy") as scan:
            for offer in (self.offer, None, object()):
                with self.subTest(offer=type(offer).__name__), \
                        self.assertRaises(view.SanitizedPDFViewError):
                    view.view_sanitized_pdf(offer, user_requested=True)
            for key, value in (("permits_open", True), ("rasterized", False)):
                forged = SanitizedCopyOffer(self.offer.pdf_bytes, 1)
                object.__setattr__(forged, key, value)
                with self.assertRaises(view.SanitizedPDFViewError):
                    view.view_sanitized_pdf(forged, user_requested=True)
            stage.assert_not_called()
            scan.assert_not_called()

    def test_symlink_substitution_blocks_and_never_deletes_victim(self):
        from tempfile import TemporaryDirectory
        with TemporaryDirectory() as folder:
            victim = Path(folder) / "victim.pdf"
            victim.write_bytes(b"keep user data")
            paths = []
            def swap(path, offer):
                path = Path(path)
                paths.append(path)
                path.unlink()
                path.symlink_to(victim)
                return self.clean()
            with patch("maximum_sanitized_copy._passive_pages", return_value=True), \
                    patch.object(view, "_scan_staged_copy", side_effect=swap), \
                    self.assertRaises(view.SanitizedPDFViewError):
                view.view_sanitized_pdf(self.offer, user_requested=True)
            self.assertEqual(victim.read_bytes(), b"keep user data")
            self.assertTrue(paths[0].is_symlink())
            # A replacement never gets removed by the failed cleanup.
            paths[0].unlink()
            paths[0].parent.rmdir()

    def test_installed_handler_unchanged_and_real_gate_is_reused(self):
        root = Path(__file__).resolve().parents[2]
        scanner = (root / "scan-and-open.py").read_text()
        handoff = (root / "maximum_safe_copy_handoff.py").read_text()
        self.assertIn("def scan_and_open_generated_copy(item, offer):", scanner)
        self.assertIn("module.scan_and_open_generated_copy(str(path), offer)", handoff)
        self.assertNotIn("maximum_view_sanitized_pdf", scanner)
        from protection_profiles import PROTECTION_PROFILES, ProtectionProfileID
        self.assertFalse(PROTECTION_PROFILES[ProtectionProfileID.MAXIMUM].selectable)


if __name__ == "__main__":
    unittest.main()
