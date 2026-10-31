#!/usr/bin/env python3
"""macOS: scanned opening of real Chrome-downloaded PDF fixtures (opener-0822).

The preceding real Chrome browser test downloads these files over HTTP and
moves them without copying or changing their original extended attributes.
This test never invokes a real scanner, Launch Services, or a user's PDF app.
"""

from contextlib import ExitStack
import errno
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
spec = importlib.util.spec_from_file_location("scan_and_open", ROOT / "scan-and-open.py")
opener = importlib.util.module_from_spec(spec)
spec.loader.exec_module(opener)

QUARANTINE = "com.apple.quarantine"
SYNTHETIC_QUARANTINE = (
    b"0081;00000000;PDFMagicChromeTest;00000000-0000-0000-0000-000000000000"
)
EXPECTED_NAMES = ("pdfmagic-attachment.pdf", "pdfmagic-octet.pdf")


@unittest.skipUnless(sys.platform == "darwin" and hasattr(os, "setxattr"),
                     "Real Chrome handoff and macOS quarantine require macOS")
class ChromeDownloadedQuarantineTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        directory = os.environ.get("PDF_MAGIC_CHROME_DOWNLOAD_DIR")
        if not directory:
            raise AssertionError(
                "CI must provide verified downloads from real Chrome; "
                "a synthetic PDF alone is not sufficient")
        cls.download_dir = Path(directory).resolve(strict=True)
        if not cls.download_dir.is_dir() or cls.download_dir.is_symlink():
            raise AssertionError("Chrome handoff path must be an existing real directory")
        if sorted(p.name for p in cls.download_dir.iterdir()) != sorted(EXPECTED_NAMES):
            raise AssertionError("The Chrome handoff must contain precisely the two PDFs")

    def _scan(self, pdf, cache, *, outcome, launch_calls, expected_quarantine):
        calls = []
        original_bytes = pdf.read_bytes()

        def fake_run(command, **kwargs):
            self.assertEqual(command[-1], str(pdf))
            self.assertEqual(command[-2], "--")
            self.assertEqual(command[0], "/scanner")
            calls.append((command, kwargs))
            if outcome == "clean":
                return subprocess.CompletedProcess(
                    command, 0, str(pdf) + ": OK\n", "")
            if outcome == "malware":
                return subprocess.CompletedProcess(
                    command, 1, str(pdf) + ": Eicar-Test-Signature FOUND\n", "")
            if outcome == "failure":
                return subprocess.CompletedProcess(
                    command, 2, "", "scanner unavailable")
            if outcome == "timeout":
                raise subprocess.TimeoutExpired(command, 5)
            raise AssertionError("Unknown simulated scanner result")

        def safe_launch(path, **kwargs):
            self.assertEqual(Path(path), pdf)
            self.assertEqual(kwargs["target_app"], "com.google.Chrome")
            self.assertEqual(os.getxattr(pdf, QUARANTINE), expected_quarantine)
            self.assertEqual(pdf.read_bytes(), original_bytes)
            launch_calls.append(Path(path))

        with ExitStack() as stack:
            stack.enter_context(patch.object(opener, "CACHE_DB", cache))
            stack.enter_context(patch.object(opener, "SCAN_REQUEST_DB", cache.parent / "audit.sqlite"))
            stack.enter_context(patch.object(opener, "intended_destination",
                                             return_value="com.google.Chrome"))
            stack.enter_context(patch.object(opener, "pdf_fallback_application",
                                             return_value=None))
            stack.enter_context(patch.object(opener, "record_scan_destination"))
            stack.enter_context(patch.object(opener, "record_opened_document_origin"))
            stack.enter_context(patch.object(opener, "verify_launch_target"))
            stack.enter_context(patch.object(opener, "read_signature_database_version",
                                             return_value=None))
            stack.enter_context(patch.object(opener, "scan_engine_version",
                                             return_value=None))
            run = stack.enter_context(patch.object(opener, "run_scan_command",
                                                  side_effect=fake_run))
            launch = stack.enter_context(patch.object(opener, "launch_clean_file",
                                                     side_effect=safe_launch))
            if outcome == "clean":
                fresh = opener.scan_and_open(str(pdf), "/scanner")
                cached = opener.scan_and_open(str(pdf), "/scanner")
                self.assertIs(fresh.from_cache, False)
                self.assertIs(cached.from_cache, True)
                self.assertEqual(run.call_count, 1,
                                 "Clean cache hit must not silently rescan")
                self.assertEqual(launch.call_count, 2,
                                 "Both fresh and cached clean scans may reach handoff")
            else:
                with self.assertRaises(RuntimeError):
                    opener.scan_and_open(str(pdf), "/scanner")
                self.assertEqual(run.call_count, 1)
                launch.assert_not_called()
            self.assertEqual(len(calls), 1)
        self.assertEqual(pdf.read_bytes(), original_bytes)
        self.assertEqual(os.getxattr(pdf, QUARANTINE), expected_quarantine)

    def test_real_chrome_downloads_preserve_quarantine_during_safe_open_handoff(self):
        pdfs = [self.download_dir / name for name in EXPECTED_NAMES]
        self.assertEqual(pdfs[0].read_bytes(), pdfs[1].read_bytes(),
                         "Two actual Chrome download routes must save identical PDF bytes")
        for pdf in pdfs:
            with self.subTest(pdf=pdf.name):
                self.assertTrue(pdf.is_file() and not pdf.is_symlink())
                original_bytes = pdf.read_bytes()
                self.assertTrue(original_bytes.startswith(b"%PDF-1.4\n"))
                self.assertTrue(original_bytes.rstrip().endswith(b"%%EOF"))
                self.assertIn(b"PDF Magic Native Download Smoke", original_bytes)
                # Headless Chrome may not attach Gatekeeper quarantine on a
                # synthetic loopback URL. If missing, label only this disposable
                # downloaded test file, then assert the scan/open gate retains it.
                try:
                    original_quarantine = os.getxattr(pdf, QUARANTINE)
                except OSError as error:
                    if error.errno not in {getattr(errno, "ENOATTR", -1), errno.ENODATA}:
                        raise
                    os.setxattr(pdf, QUARANTINE, SYNTHETIC_QUARANTINE)
                    original_quarantine = os.getxattr(pdf, QUARANTINE)
                self.assertTrue(original_quarantine)
                launched = []
                with tempfile.TemporaryDirectory(prefix="chrome-pdf-open-gate-") as tmp:
                    root = Path(tmp)
                    self._scan(pdf, root / "clean.sqlite", outcome="clean",
                               launch_calls=launched,
                               expected_quarantine=original_quarantine)
                    self.assertEqual(launched, [pdf, pdf])
                    for outcome in ("malware", "failure", "timeout"):
                        with self.subTest(outcome=outcome):
                            launched.clear()
                            self._scan(pdf, root / (outcome + ".sqlite"),
                                       outcome=outcome, launch_calls=launched,
                                       expected_quarantine=original_quarantine)
                            self.assertEqual(launched, [],
                                             "Failed scans may never hand off a file")
                self.assertEqual(pdf.read_bytes(), original_bytes)
                self.assertEqual(os.getxattr(pdf, QUARANTINE), original_quarantine)


if __name__ == "__main__":
    unittest.main()
