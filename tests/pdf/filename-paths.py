#!/usr/bin/env python3
"""Regression coverage for PDF filenames and literal paths across scan and launch."""
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

FILENAMES = (
    "Quarterly Report.PDF",
    "Café_日本語_🚀.pdf",
    "report #5; '$HOME' & [draft] (100%).pdf",
    "--not-an-option $*?.pdf",
)


class PDFFilenameTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory(prefix="pdf-paths-")
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name).resolve() / "folder with spaces & #"
        self.root.mkdir()
        for name, value in (
            ("CACHE_DB", self.root / "clean-scan-cache.sqlite3"),
            ("SCAN_REQUEST_DB", self.root / "scan-requests.sqlite3"),
        ):
            setting = patch.object(opener, name, value)
            setting.start()
            self.addCleanup(setting.stop)
        target = patch("file_launcher.TARGET_APP_CONFIG", self.root / "target-app.txt")
        target.start()
        self.addCleanup(target.stop)

    def test_original_pdf_name_is_preserved_from_scan_through_launch(self):
        """Neither ClamAV nor the approved launcher receives a shell-expanded path."""
        from file_launcher import NATIVE_LAUNCHER
        for index, filename in enumerate(FILENAMES):
            with self.subTest(filename=filename):
                pdf = self.root / filename
                original = ("%PDF-1.7\n" + str(index)).encode("utf-8")
                pdf.write_bytes(original)
                calls = []

                def run(command, **kwargs):
                    calls.append(command)
                    if command[0] == "/scanner":
                        return subprocess.CompletedProcess(command, 0, "file: OK\n", "")
                    return subprocess.CompletedProcess(command, 0, "", "")

                with patch.object(opener.subprocess, "run", side_effect=run), \
                        patch.object(opener.subprocess, "check_output",
                                     side_effect=FileNotFoundError), \
                        patch.object(opener, "read_signature_database_version",
                                     return_value=None), \
                        patch.object(opener, "remove_quarantine") as quarantine, \
                        patch.object(opener, "verify_launch_target") as verify:
                    result = opener.scan_and_open(str(pdf), "/scanner")

                self.assertEqual(result.status, "clean")
                self.assertEqual(len(calls), 2)
                scan, launch = calls
                self.assertEqual(scan[0], "/scanner")
                self.assertEqual(scan[-2:], ["--", str(pdf)])
                proof = ":".join(map(str, opener.file_identity(pdf)[0][1:]))
                self.assertEqual(
                    launch,
                    [str(NATIVE_LAUNCHER), "--expected-identity", proof,
                     "--bundle-id", "com.brave.Browser", str(pdf)],
                )
                verify.assert_called_once_with(pdf, target_app="com.brave.Browser")
                quarantine.assert_called_once_with(pdf)
                self.assertEqual(pdf.read_bytes(), original)
                self.assertEqual(pdf.name, filename)
                self.assertTrue(pdf.is_file())

    def test_shared_finder_and_native_shell_gate_preserves_literal_pdf_argument(self):
        """The shell entry point forwards one literal argument, not a command string."""
        source = (ROOT / "allow-and-open.sh").read_text(encoding="utf-8")
        original = 'exec /usr/bin/python3 "$script_dir/scan-and-open.py" "$@"'
        self.assertEqual(source.count(original), 1)
        gate = self.root / "allow-and-open.sh"
        gate.write_text(
            source.replace(original, 'exec /bin/bash "$script_dir/capture.sh" "$@"'),
            encoding="utf-8",
        )
        (self.root / "capture.sh").write_text('printf "%s\\0" "$@"\n', encoding="utf-8")
        for filename in FILENAMES:
            with self.subTest(filename=filename):
                pdf = self.root / filename
                pdf.write_bytes(b"%PDF-1.7\n")
                result = subprocess.run(
                    ["/bin/bash", str(gate), str(pdf)],
                    capture_output=True, check=True,
                    env={**os.environ, "PDF_MAGIC_REQUESTING_APPLICATION": "PDF Magic Opener"},
                )
                self.assertEqual(result.stdout, os.fsencode(str(pdf)) + b"\0")
                self.assertTrue(pdf.exists())


if __name__ == "__main__":
    unittest.main()
