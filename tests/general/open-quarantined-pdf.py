#!/usr/bin/env python3
"""opener-0820: quarantined PDF scan-to-open acceptance tests, without GUI launch.

Only synthetic PDF files under a disposable temporary directory are used.
The actual scan-and-open gate runs, but the ClamAV process, external native
launcher and browser destinations are isolated test doubles. On macOS, the
test uses real com.apple.quarantine extended attributes.
"""

from contextlib import ExitStack
import importlib.util
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location("scan_and_open", ROOT / "scan-and-open.py")
opener = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(opener)

ATTRIBUTE = "com.apple.quarantine"
MARKER = b"0081;00000000;PDFMagicOpener;00000000-0000-0000-0000-000000000000"
SELECTED_BROWSER = "com.google.Chrome"
MACOS_XATTR = sys.platform == "darwin" and hasattr(os, "getxattr") and hasattr(os, "setxattr")


class OpenQuarantinedPDFTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="pdf-magic-open-quarantine-")
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name).resolve()
        self.pdf = self.root / "synthetic-downloaded.pdf"
        self.pdf.write_bytes(
            b"%PDF-1.4\n"
            b"1 0 obj\n<</Type/Catalog/Pages 2 0 R>>\nendobj\n"
            b"2 0 obj\n<</Type/Pages/Count 0/Kids[]>>\nendobj\n"
            b"trailer\n<</Root 1 0 R>>\n%%EOF\n"
        )
        self.original = self.pdf.read_bytes()
        self.expected_quarantine = False

    def tag(self):
        if not MACOS_XATTR:
            self.skipTest("Real quarantine xattrs require macOS")
        os.setxattr(self.pdf, ATTRIBUTE, MARKER)
        self.expected_quarantine = True
        self.assertEqual(os.getxattr(self.pdf, ATTRIBUTE), MARKER)

    def tagged(self):
        if self.expected_quarantine:
            self.assertEqual(os.getxattr(self.pdf, ATTRIBUTE), MARKER)
        self.assertEqual(self.pdf.read_bytes(), self.original)

    def attempt(self, *, verdict="clean", cached=False, invalid_destination=False,
                failed_launch=False, change_during_scan=False):
        events = []
        with ExitStack() as stack:
            stack.enter_context(patch.object(opener, "CACHE_DB", self.root / "cache.sqlite"))
            stack.enter_context(patch.object(opener, "SCAN_REQUEST_DB", self.root / "requests.sqlite"))
            stack.enter_context(patch.object(opener, "intended_destination",
                                             return_value=SELECTED_BROWSER))
            stack.enter_context(patch.object(opener, "pdf_fallback_application",
                                             return_value=None))
            stack.enter_context(patch.object(opener, "record_scan_destination",
                                             side_effect=lambda dest: events.append(("selected", dest))))
            stack.enter_context(patch.object(opener, "record_opened_document_origin",
                                             side_effect=lambda origin: events.append(("opened", origin))))
            stack.enter_context(patch.object(opener, "scan_engine_version", return_value=None))
            stack.enter_context(patch.object(opener, "read_signature_database_version",
                                             return_value=None))
            stack.enter_context(patch.object(opener, "verify_local_file_available",
                                             side_effect=lambda path: events.append(("local", path))))
            original_hook = opener.remove_quarantine
            stack.enter_context(patch.object(opener, "remove_quarantine",
                                             wraps=original_hook))
            remove = opener.remove_quarantine

            def verify_target(path, target_app=None):
                self.assertEqual(path, self.pdf)
                self.assertEqual(target_app, SELECTED_BROWSER)
                self.tagged()
                events.append(("verified-target", target_app))
                if invalid_destination:
                    raise RuntimeError("The selected PDF application is unavailable.")

            stack.enter_context(patch.object(opener, "verify_launch_target",
                                             side_effect=verify_target))

            def scan(command, **kwargs):
                self.assertEqual(command[0], "/mock-clamscan")
                self.assertEqual(command[-1], str(self.pdf))
                self.assertEqual(command[-2], "--")
                self.assertNotIn("xattr", " ".join(command))
                self.tagged()
                events.append(("scanned", str(self.pdf)))
                if change_during_scan:
                    self.pdf.write_bytes(self.original + b"\n%mutated-after-scanning")
                if verdict == "timeout":
                    raise subprocess.TimeoutExpired(command, 1)
                if verdict == "malware":
                    return subprocess.CompletedProcess(command, 1,
                        "synthetic-downloaded.pdf: Eicar-Test-Signature FOUND", "")
                return subprocess.CompletedProcess(command, 0,
                    "synthetic-downloaded.pdf: OK", "")

            scan_mock = stack.enter_context(patch.object(
                opener, "run_scan_command", side_effect=scan))

            def launch(path, *, target_app=None):
                self.assertEqual(path, self.pdf)
                self.assertEqual(target_app, SELECTED_BROWSER)
                self.tagged()
                events.append(("handoff", target_app))
                if failed_launch:
                    raise OSError("Test-only native application launch failure")

            launch_mock = stack.enter_context(patch.object(
                opener, "launch_clean_file", side_effect=launch))

            def invoke():
                return opener.scan_and_open(str(self.pdf), "/mock-clamscan")

            if verdict == "clean" and not invalid_destination and not failed_launch and not change_during_scan:
                first = invoke()
                self.assertEqual(first.from_cache, False)
                self.tagged()
                if cached:
                    second = invoke()
                    self.assertEqual(second.from_cache, True)
            else:
                error = ("Malware" if verdict == "malware" else
                         "timed out" if verdict == "timeout" else
                         "unavailable" if invalid_destination else
                         "changed" if change_during_scan else
                         "could not open" if failed_launch else "")
                with self.assertRaisesRegex((RuntimeError, OSError), error):
                    invoke()
            self.assertEqual(scan_mock.call_count, 1)
            self.assertEqual(launch_mock.call_count,
                (2 if cached else 1) if verdict == "clean" and not (
                    invalid_destination or change_during_scan) else 0)
            if verdict == "clean" and not invalid_destination and not change_during_scan:
                remove.assert_called_once_with(self.pdf) if failed_launch else (
                    self.assertEqual(remove.call_count, 2) if cached
                    else remove.assert_called_once_with(self.pdf))
            else:
                remove.assert_not_called()
        return events

    def test_portable_clean_open_uses_verified_selected_browser_and_same_file(self):
        events = self.attempt()
        self.assertIn(("verified-target", SELECTED_BROWSER), events)
        self.assertIn(("handoff", SELECTED_BROWSER), events)
        self.assertEqual(events[-1], ("opened", "original"))

    @unittest.skipUnless(MACOS_XATTR, "Real macOS quarantine xattrs only")
    def test_quarantined_pdf_is_handed_off_only_after_clean_scan_and_verified_destination(self):
        self.tag()
        events = self.attempt(cached=True)
        self.tagged()
        self.assertEqual(events.count(("scanned", str(self.pdf))), 1)
        self.assertEqual(events.count(("handoff", SELECTED_BROWSER)), 2)
        self.assertEqual(events.count(("opened", "original")), 2)
        self.assertLess(events.index(("scanned", str(self.pdf))),
                        events.index(("verified-target", SELECTED_BROWSER)))
        self.assertLess(events.index(("verified-target", SELECTED_BROWSER)),
                        events.index(("handoff", SELECTED_BROWSER)))

    @unittest.skipUnless(MACOS_XATTR, "Real macOS quarantine xattrs only")
    def test_quarantined_malicious_or_timed_out_pdf_is_never_opened(self):
        for verdict in ("malware", "timeout"):
            with self.subTest(verdict=verdict):
                # Independent test data/cache so one result cannot authorize another.
                self.pdf.write_bytes(self.original)
                self.tag()
                events = self.attempt(verdict=verdict)
                self.tagged()
                self.assertNotIn(("handoff", SELECTED_BROWSER), events)
                self.assertFalse(any(event[0] == "opened" for event in events))

    @unittest.skipUnless(MACOS_XATTR, "Real macOS quarantine xattrs only")
    def test_quarantined_pdf_with_unverified_destination_is_not_opened(self):
        self.tag()
        events = self.attempt(invalid_destination=True)
        self.tagged()
        self.assertNotIn(("handoff", SELECTED_BROWSER), events)

    @unittest.skipUnless(MACOS_XATTR, "Real macOS quarantine xattrs only")
    def test_quarantined_pdf_native_launcher_failure_does_not_remove_quarantine(self):
        self.tag()
        events = self.attempt(failed_launch=True)
        self.tagged()
        self.assertIn(("handoff", SELECTED_BROWSER), events)
        self.assertNotIn(("opened", "original"), events)

    @unittest.skipUnless(MACOS_XATTR, "Real macOS quarantine xattrs only")
    def test_pdf_bytes_changed_after_clean_scan_never_reach_launcher(self):
        self.tag()
        original = self.original
        try:
            events = self.attempt(change_during_scan=True)
            self.assertNotIn(("handoff", SELECTED_BROWSER), events)
            self.assertEqual(os.getxattr(self.pdf, ATTRIBUTE), MARKER)
        finally:
            self.pdf.write_bytes(original)
        self.tagged()


if __name__ == "__main__":
    unittest.main()
