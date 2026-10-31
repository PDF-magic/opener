#!/usr/bin/env python3
"""opener-0861: real unexpectedly exiting helpers must never authorize a PDF open."""
from contextlib import nullcontext
import importlib.util
from pathlib import Path
import signal
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

import file_launcher

ROOT = Path(__file__).resolve().parents[2]
sys.dont_write_bytecode = True
spec = importlib.util.spec_from_file_location("unexpected_exit_gate", ROOT / "scan-and-open.py")
gate = importlib.util.module_from_spec(spec)
spec.loader.exec_module(gate)


class UnexpectedHelperExitTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="opener-helper-exit-")
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.pdf = self.root / "selected report.pdf"
        self.original = b"%PDF-1.4\nSynthetic scan fixture\n"
        self.pdf.write_bytes(self.original)
        for name, value in (
            ("CACHE_DB", self.root / "clean-cache.sqlite3"),
            ("SCAN_REQUEST_DB", self.root / "requests.sqlite3"),
        ):
            p = patch.object(gate, name, value)
            p.start()
            self.addCleanup(p.stop)
        # This suite exercises real synthetic scanner process exits, but its
        # executable and database are intentionally not an installed ClamAV.
        # Keep the child subprocess real; only the separate Seatbelt admission
        # boundary is mocked. Kernel-denial tests cover the production sandbox.
        sandbox = patch.object(
            gate, "confined_scanner",
            side_effect=lambda command, *, scan: nullcontext((command, {})))
        sandbox.start()
        self.addCleanup(sandbox.stop)

    def executable(self, name, body):
        path = self.root / name
        path.write_text(f"#!{sys.executable}\n" + body, encoding="utf-8")
        path.chmod(0o700)
        return str(path)

    def scanner(self, *, scan_exit="sys.exit(0)", version_exit="sys.exit(0)"):
        return self.executable(
            "synthetic-clamscan.py",
            "import os, signal, sys\n"
            "if '--version' in sys.argv:\n"
            "    print('ClamAV 1.4.3', flush=True)\n"
            f"    {version_exit}\n"
            "print('file: OK', flush=True)\n"
            f"{scan_exit}\n",
        )

    def isolated_gate(self):
        """Replace only external OS integrations, never the real scan subprocess."""
        from contextlib import ExitStack
        stack = ExitStack()
        self.addCleanup(stack.close)
        for name, value in (
            ("intended_destination", "com.brave.Browser"),
            ("pdf_fallback_application", None),
            ("verify_local_file_available", None),
            ("verify_launch_target", None),
            ("record_scan_destination", None),
            ("read_signature_database_version", None),
            ("remove_quarantine", None),
            ("record_opened_document_origin", None),
        ):
            stack.enter_context(patch.object(gate, name, return_value=value))
        return stack

    def test_scanner_early_exit_or_signal_cannot_publish_clean_verdict(self):
        for label, exit_code in (
            ("nonzero", "sys.exit(7)"),
            ("killed", "os.kill(os.getpid(), signal.SIGKILL)"),
            ("empty-success", "sys.stdout.flush(); sys.exit(0)"),
        ):
            with self.subTest(label=label):
                if label == "empty-success":
                    script = self.executable(
                        "synthetic-clamscan.py",
                        "import sys\n"
                        "if '--version' in sys.argv:\n"
                        "    print('ClamAV 1.4.3'); sys.exit(0)\n"
                        "sys.exit(0)\n",
                    )
                else:
                    script = self.scanner(scan_exit=exit_code)
                self.isolated_gate()
                with patch.object(gate, "run_scan_command", wraps=gate.run_scan_command) as scan, \
                     patch.object(gate, "remember_clean") as cache, \
                     patch.object(gate, "launch_clean_file") as launch, \
                     patch.object(gate, "remove_quarantine") as quarantine, \
                     patch.object(gate, "record_opened_document_origin") as opened:
                    with self.assertRaises(RuntimeError) as error:
                        gate.scan_and_open(str(self.pdf), script)
                scan.assert_called_once()
                cache.assert_not_called()
                launch.assert_not_called()
                quarantine.assert_not_called()
                opened.assert_not_called()
                self.assertIn("opening was stopped", str(error.exception))
                self.assertNotIn(str(self.pdf), str(error.exception))
                self.assertEqual(self.pdf.read_bytes(), self.original)

    def test_version_helper_crash_cannot_admit_a_scanner(self):
        for label, exit_code in (
            ("nonzero", "sys.exit(7)"),
            ("killed", "os.kill(os.getpid(), signal.SIGKILL)"),
        ):
            with self.subTest(label=label):
                scanner = self.scanner(version_exit=exit_code)
                with patch.object(gate, "detect_clamav_installation", return_value=scanner), \
                     patch.object(gate, "run_scan_command") as scan, \
                     patch.object(gate, "launch_clean_file") as launch:
                    with self.assertRaisesRegex(RuntimeError, "version could not be verified"):
                        gate.scanner_path()
                scan.assert_not_called()
                launch.assert_not_called()
                self.assertEqual(self.pdf.read_bytes(), self.original)

    def test_native_launcher_crash_after_clean_scan_does_not_report_open(self):
        scanner = self.scanner()
        for label, exit_code in (
            ("nonzero", "sys.exit(7)"),
            ("killed", "os.kill(os.getpid(), signal.SIGKILL)"),
        ):
            with self.subTest(label=label):
                # A distinct digest forces a fresh genuine scan in each case.
                expected = self.original + label.encode("ascii")
                self.pdf.write_bytes(expected)
                helper = self.executable(
                    "synthetic-launcher.py",
                    "import os, signal, sys\n" + exit_code + "\n",
                )
                self.isolated_gate()
                with patch.object(file_launcher, "NATIVE_LAUNCHER", Path(helper)), \
                     patch.object(gate, "record_opened_document_origin") as opened, \
                     patch.object(gate, "remember_clean", wraps=gate.remember_clean) as cache:
                    with self.assertRaises(gate.LaunchFailedError):
                        # Use the real launch_clean_file function and its checked subprocess.
                        gate.scan_and_open(str(self.pdf), scanner)
                cache.assert_called_once()
                opened.assert_not_called()
                self.assertEqual(self.pdf.read_bytes(), expected)

    def test_native_verifier_crash_after_clean_scan_blocks_launch(self):
        scanner = self.scanner()
        helper = self.executable(
            "synthetic-verifier.py",
            "import os, signal\n"
            "os.kill(os.getpid(), signal.SIGKILL)\n",
        )
        self.isolated_gate()
        with patch.object(gate, "verify_launch_target", wraps=file_launcher.verify_launch_target), \
             patch.object(file_launcher, "PDF_TARGET_VERIFIER", Path(helper)), \
             patch.object(gate, "launch_clean_file") as launch, \
             patch.object(gate, "record_opened_document_origin") as opened:
            with self.assertRaisesRegex(RuntimeError, "application"):
                gate.scan_and_open(str(self.pdf), scanner)
        launch.assert_not_called()
        opened.assert_not_called()
        self.assertEqual(self.pdf.read_bytes(), self.original)


if __name__ == "__main__":
    unittest.main()
