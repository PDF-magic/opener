#!/usr/bin/env python3
"""Regression for opener-0277: keep operating-system quarantine after scanning."""

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
ROOT = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location("scan_and_open", ROOT / "scan-and-open.py")
opener = importlib.util.module_from_spec(spec)
spec.loader.exec_module(opener)

QUARANTINE_ATTRIBUTE = "com.apple.quarantine"
TEST_QUARANTINE_VALUE = b"0081;00000000;PDFMagicOpener;00000000-0000-0000-0000-000000000000"


class RetainOperatingSystemQuarantineTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="pdf-magic-quarantine-")
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name).resolve()
        self.pdf = self.root / "downloaded.pdf"
        self.pdf.write_bytes(b"%PDF-1.4\n1 0 obj <</Type /Catalog>> endobj\n%%EOF\n")

    def scan(self, path, *, verdict=0):
        """Run the actual scan gate with no real scanner, app or user preferences."""
        scans = []
        launched = []
        with ExitStack() as stack:
            stack.enter_context(patch.object(opener, "CACHE_DB", self.root / "cache.sqlite"))
            stack.enter_context(patch.object(opener, "SCAN_REQUEST_DB", self.root / "audit.sqlite"))
            stack.enter_context(patch.object(opener, "intended_destination",
                                             return_value="com.brave.Browser"))
            stack.enter_context(patch.object(opener, "pdf_fallback_application",
                                             return_value=None))
            stack.enter_context(patch.object(opener, "record_scan_destination"))
            stack.enter_context(patch.object(opener, "verify_launch_target"))
            stack.enter_context(patch.object(opener, "verify_local_file_available"))
            stack.enter_context(patch.object(opener, "scan_engine_version",
                                             return_value=None))
            stack.enter_context(patch.object(opener, "read_signature_database_version",
                                             return_value=None))
            stack.enter_context(patch.object(opener, "launch_clean_file",
                                             side_effect=lambda *args, **kwargs: launched.append(args)))
            def run(command, **kwargs):
                scans.append(command)
                if verdict == 0:
                    return subprocess.CompletedProcess(command, 0, "downloaded.pdf: OK", "")
                return subprocess.CompletedProcess(command, 1,
                                                   "downloaded.pdf: Eicar-Test-Signature FOUND", "")
            stack.enter_context(patch.object(opener.subprocess, "run", side_effect=run))
            if verdict == 0:
                fresh = opener.scan_and_open(str(path), "/scanner")
                cached = opener.scan_and_open(str(path), "/scanner")
                self.assertEqual((fresh.from_cache, cached.from_cache), (False, True))
                self.assertEqual(len(scans), 1, "Cached clean scan must reuse a verified result")
                self.assertEqual(len(launched), 2)
            else:
                with self.assertRaisesRegex(RuntimeError, "Malware"):
                    opener.scan_and_open(str(path), "/scanner")
                self.assertEqual(len(scans), 1)
                self.assertEqual(launched, [])
            for command in scans:
                self.assertEqual(command[0], "/scanner")
                self.assertNotIn("/usr/bin/xattr", command)
        return scans, launched

    def test_legacy_hook_never_strips_quarantine_or_launches_anything(self):
        source = (ROOT / "scan-and-open.py").read_text(encoding="utf-8")
        hook = source.split("def remove_quarantine(path):", 1)[1].split(
            "\n@dataclass(frozen=True)", 1)[0]
        self.assertNotIn("subprocess", hook)
        self.assertNotIn("os.removexattr", hook)
        self.assertNotIn("xattr", hook.split('"""', 2)[-1])
        with patch.object(opener.subprocess, "run") as run:
            opener.remove_quarantine(self.pdf)
            run.assert_not_called()

    def test_clean_cached_and_blocked_pdf_keep_scan_and_handoff_safety(self):
        self.scan(self.pdf)
        other = self.root / "blocked.pdf"
        other.write_bytes(self.pdf.read_bytes() + b"\n%blocked")
        self.scan(other, verdict=1)

    @unittest.skipUnless(sys.platform == "darwin" and hasattr(os, "setxattr"),
                         "macOS quarantine extended attributes only")
    def test_macos_quarantine_attribute_survives_fresh_and_cached_clean_pdf(self):
        os.setxattr(self.pdf, QUARANTINE_ATTRIBUTE, TEST_QUARANTINE_VALUE)
        original = os.getxattr(self.pdf, QUARANTINE_ATTRIBUTE)
        self.scan(self.pdf)
        self.assertEqual(os.getxattr(self.pdf, QUARANTINE_ATTRIBUTE), original)

    @unittest.skipUnless(sys.platform == "darwin" and hasattr(os, "setxattr"),
                         "macOS quarantine extended attributes only")
    def test_macos_quarantine_attribute_survives_blocked_pdf(self):
        os.setxattr(self.pdf, QUARANTINE_ATTRIBUTE, TEST_QUARANTINE_VALUE)
        original = os.getxattr(self.pdf, QUARANTINE_ATTRIBUTE)
        self.scan(self.pdf, verdict=1)
        self.assertEqual(os.getxattr(self.pdf, QUARANTINE_ATTRIBUTE), original)


if __name__ == "__main__":
    unittest.main()
