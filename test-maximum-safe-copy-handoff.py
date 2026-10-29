#!/usr/bin/env python3
"""opener-0320: source must never be the PDF handed to a viewer."""
from dataclasses import FrozenInstanceError
from io import BytesIO
from pathlib import Path
import sys
from types import SimpleNamespace
import os
import tempfile
import unittest
from unittest.mock import patch

from pypdf import PdfWriter
import maximum_safe_copy_handoff as route
from maximum_sanitized_copy import SanitizedCopyOffer
from scan_results import EFFECTIVE_POLICY_ID


def pdf():
    writer = PdfWriter()
    writer.add_blank_page(width=100, height=120)
    output = BytesIO()
    writer.write(output)
    return output.getvalue()


class MaximumSafeCopyRoutingTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.source = Path(self.temporary.name) / "source.pdf"
        self.original = pdf()
        self.source.write_bytes(self.original)

    def _offer(self):
        # The trusted converter is independently covered by opener-0313/0315.
        return SanitizedCopyOffer(b"%PDF-copy fixture", 1)

    def _open(self, scan=None):
        if scan is None:
            scan = lambda p, s: SimpleNamespace(
                status="clean", effective_policy_id=EFFECTIVE_POLICY_ID,
                from_cache=False)
        with patch.object(route, "offer_sanitized_pdf_copy", return_value=self._offer()), \
                patch.object(route, "_passive_pages", return_value=True), \
                patch.object(route, "_scan_staged_copy", side_effect=scan):
            return route.open_required_maximum_safe_copy(
                self.source,
                disposition=route.MaximumCopyDisposition.REQUIRED)

    def test_required_policy_opens_only_private_separately_scanned_copy(self):
        requests = []
        def scan(path, offer):
            path = Path(path)
            requests.append((path, offer.pdf_bytes, path.read_bytes()))
            self.assertNotEqual(path.resolve(), self.source.resolve())
            self.assertEqual(path.name, "safe-copy.pdf")
            self.assertEqual(stat_mode(path), 0o600)
            self.assertEqual(stat_mode(path.parent), 0o700)
            self.assertEqual(self.source.read_bytes(), self.original)
            return SimpleNamespace(status="clean", effective_policy_id=EFFECTIVE_POLICY_ID,
                from_cache=False)
        handoff = self._open(scan)
        self.addCleanup(route._discard_private_copy, handoff.copy_path)
        self.assertEqual(requests[0][2], self._offer().pdf_bytes)
        self.assertEqual(requests[0][1], self._offer().pdf_bytes)
        self.assertEqual(handoff.copy_path, requests[0][0])
        self.assertTrue(handoff.scanned)
        self.assertFalse(handoff.original_opened)
        with self.assertRaises(FrozenInstanceError):
            handoff.original_opened = True

    def test_required_mode_is_explicit_no_implicit_source_fallback(self):
        for value in (None, False, True, "required", "maximum"):
            with self.subTest(value=value), patch.object(
                route, "_read_source"
            ) as read, self.assertRaises(route.MaximumSafeCopyError):
                route.open_required_maximum_safe_copy(
                    self.source, disposition=value)
            read.assert_not_called()

    def test_unavailable_or_invalid_copy_never_scans_or_opens_source(self):
        bad = (None, SanitizedCopyOffer(self.source.read_bytes(), 1),
               SanitizedCopyOffer(b"%PDF-unsafe", 1))
        for offered in bad:
            with self.subTest(offered=offered), patch.object(
                route, "offer_sanitized_pdf_copy", return_value=offered
            ), patch.object(route, "_scan_staged_copy") as launch:
                with self.assertRaises(route.MaximumSafeCopyError):
                    route.open_required_maximum_safe_copy(
                        self.source,
                        disposition=route.MaximumCopyDisposition.REQUIRED)
                launch.assert_not_called()

    def test_failed_copy_scan_or_launch_never_retries_original(self):
        for response in (None, SimpleNamespace(status="infected",
                                                effective_policy_id=EFFECTIVE_POLICY_ID,
                                   from_cache=False),
                         SimpleNamespace(status="clean", effective_policy_id="maximum"),
                         SimpleNamespace(status="clean", effective_policy_id=EFFECTIVE_POLICY_ID,
                                         from_cache=True),
                         RuntimeError("private original source filename")):
            paths = []
            def scan(path, offer):
                paths.append(Path(path))
                if isinstance(response, Exception):
                    raise response
                return response
            with self.subTest(response=type(response).__name__):
                with self.assertRaises(route.MaximumSafeCopyError) as caught:
                    self._open(scan)
                self.assertEqual(str(caught.exception), route.BLOCK_MESSAGE)
                self.assertEqual(len(paths), 1)
                self.assertNotEqual(paths[0], self.source)
                self.assertFalse(paths[0].exists())
                self.assertFalse(paths[0].parent.exists())
                self.assertTrue(self.source.exists())

    def test_symlink_malformed_and_modified_sources_fail_closed(self):
        alias = Path(self.temporary.name) / "alias.pdf"
        alias.symlink_to(self.source)
        for item in (alias, "relative.pdf", self.source.with_name("missing.pdf")):
            with self.subTest(source=str(item)), patch.object(
                route, "offer_sanitized_pdf_copy"
            ) as converter, self.assertRaises(route.MaximumSafeCopyError):
                route.open_required_maximum_safe_copy(
                    item,
                    disposition=route.MaximumCopyDisposition.REQUIRED)
            converter.assert_not_called()
        self.source.write_bytes(b"%PDF-bad")
        with patch.object(route, "offer_sanitized_pdf_copy") as converter, \
                self.assertRaises(route.MaximumSafeCopyError):
            route.open_required_maximum_safe_copy(
                self.source,
                disposition=route.MaximumCopyDisposition.REQUIRED)
        # The converter is allowed to reject malformed input, never open it.
        self.assertEqual(converter.call_count, 1)

    def test_staged_file_symlink_is_blocked_before_scanner(self):
        protected = Path(self.temporary.name) / "protected.pdf"
        protected.write_bytes(b"never scan or remove this target")
        staged = []
        original_stage = route._stage_private_copy

        def swap(pdf_bytes):
            path = original_stage(pdf_bytes)
            staged.append(path)
            path.unlink()
            path.symlink_to(protected)
            return path

        with patch.object(route, "_stage_private_copy", side_effect=swap), \
                patch.object(route, "offer_sanitized_pdf_copy", return_value=self._offer()), \
                patch.object(route, "_passive_pages", return_value=True), \
                patch.object(route, "_scan_staged_copy") as scan, \
                self.assertRaises(route.MaximumSafeCopyError):
            route.open_required_maximum_safe_copy(
                self.source, disposition=route.MaximumCopyDisposition.REQUIRED)
        scan.assert_not_called()
        self.assertEqual(protected.read_bytes(), b"never scan or remove this target")
        self.assertTrue(staged[0].is_symlink())
        staged[0].unlink()
        staged[0].parent.rmdir()
        route._STAGED_LEASES.pop(staged[0], None)

    def test_staged_directory_symlink_is_blocked_before_scanner(self):
        protected = Path(self.temporary.name) / "protected-dir"
        protected.mkdir()
        sentinel = protected / "safe-copy.pdf"
        sentinel.write_bytes(b"unrelated content")
        staged = []
        original_stage = route._stage_private_copy

        def swap(pdf_bytes):
            path = original_stage(pdf_bytes)
            old_dir = path.parent.with_name(path.parent.name + "-old")
            path.parent.rename(old_dir)
            path.parent.symlink_to(protected, target_is_directory=True)
            staged.append((path, old_dir))
            return path

        with patch.object(route, "_stage_private_copy", side_effect=swap), \
                patch.object(route, "offer_sanitized_pdf_copy", return_value=self._offer()), \
                patch.object(route, "_passive_pages", return_value=True), \
                patch.object(route, "_scan_staged_copy") as scan, \
                self.assertRaises(route.MaximumSafeCopyError):
            route.open_required_maximum_safe_copy(
                self.source, disposition=route.MaximumCopyDisposition.REQUIRED)
        scan.assert_not_called()
        self.assertEqual(sentinel.read_bytes(), b"unrelated content")
        path, old_dir = staged[0]
        path.parent.unlink()
        old_dir.rename(path.parent)
        route._discard_private_copy(path)
        self.assertFalse(path.parent.exists())

    def test_symlink_replacement_during_scan_blocks_success_and_cleanup(self):
        protected = Path(self.temporary.name) / "protected.pdf"
        protected.write_bytes(b"keep")
        staged = []

        def substitute(path, offer):
            staged.append(Path(path))
            Path(path).unlink()
            Path(path).symlink_to(protected)
            return SimpleNamespace(
                status="clean", effective_policy_id=EFFECTIVE_POLICY_ID,
                from_cache=False)

        with self.assertRaises(route.MaximumSafeCopyError):
            self._open(substitute)
        self.assertEqual(protected.read_bytes(), b"keep")
        self.assertTrue(staged[0].is_symlink())
        staged[0].unlink()
        staged[0].parent.rmdir()
        route._STAGED_LEASES.pop(staged[0], None)

    def test_source_changed_during_conversion_never_launches(self):
        def modified(data):
            self.source.write_bytes(data + b"modified")
            return self._offer()
        with patch.object(route, "offer_sanitized_pdf_copy", side_effect=modified), \
                patch.object(route, "_passive_pages", return_value=True), \
                patch.object(route, "_scan_staged_copy") as scan, \
                self.assertRaises(route.MaximumSafeCopyError):
            route.open_required_maximum_safe_copy(
                self.source,
                disposition=route.MaximumCopyDisposition.REQUIRED)
        scan.assert_not_called()

    def test_failed_private_copy_write_cleans_up_without_a_scan(self):
        created = []
        mkdtemp = tempfile.mkdtemp
        def stage(*args, **kwargs):
            name = mkdtemp(*args, **kwargs)
            created.append(Path(name))
            return name
        with patch.object(route, "offer_sanitized_pdf_copy", return_value=self._offer()), \
                patch.object(route, "_passive_pages", return_value=True), \
                patch.object(route.tempfile, "mkdtemp", side_effect=stage), \
                patch.object(route.os, "fsync", side_effect=OSError("private error")), \
                patch.object(route, "_scan_staged_copy") as scanner, \
                self.assertRaises(route.MaximumSafeCopyError):
            route.open_required_maximum_safe_copy(
                self.source,
                disposition=route.MaximumCopyDisposition.REQUIRED)
        self.assertEqual(len(created), 1)
        self.assertFalse(created[0].exists())
        scanner.assert_not_called()

    @unittest.skipUnless(sys.platform == "darwin",
                         "Native sanitized conversion only runs on macOS")
    def test_real_rebuilt_copy_is_the_only_scanner_target(self):
        destination = []
        def scanner(path, offer):
            file = Path(path)
            destination.append(file)
            self.assertNotEqual(file, self.source)
            self.assertNotEqual(file.read_bytes(), self.source.read_bytes())
            self.assertTrue(file.read_bytes().startswith(b"%PDF-"))
            self.assertEqual(offer.pdf_bytes, file.read_bytes())
            return SimpleNamespace(status="clean",
                                   effective_policy_id=EFFECTIVE_POLICY_ID,
                                   from_cache=False)
        with patch.object(route, "_scan_staged_copy", side_effect=scanner):
            result = route.open_required_maximum_safe_copy(
                self.source,
                disposition=route.MaximumCopyDisposition.REQUIRED)
        self.addCleanup(route._discard_private_copy, result.copy_path)
        self.assertEqual(destination, [result.copy_path])
        self.assertFalse(result.original_opened)

    def test_normal_gate_is_the_real_existing_scanner_not_new_launcher(self):
        text = Path(route.__file__).read_text()
        self.assertIn('with_name("scan-and-open.py")', text)
        self.assertIn("module.scan_and_open_generated_copy(str(path), offer)", text)
        self.assertNotIn("launch_clean_file(source_path", text)
        scanner = (Path(route.__file__).parent / "scan-and-open.py").read_text()
        self.assertIn("def scan_and_open_generated_copy(item, offer):", scanner)
        self.assertNotIn("maximum_safe_copy_handoff", scanner)
        from protection_profiles import PROTECTION_PROFILES, ProtectionProfileID
        self.assertFalse(PROTECTION_PROFILES[ProtectionProfileID.MAXIMUM].selectable)


def stat_mode(path):
    return os.stat(path).st_mode & 0o777


if __name__ == "__main__":
    unittest.main()
