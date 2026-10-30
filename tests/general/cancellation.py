#!/usr/bin/env python3
"""Cancellation must stop a real scanner process before opening any file."""
import os
from pathlib import Path
import signal
import subprocess
import sys
import tempfile
import time
import unittest


class CancellationTests(unittest.TestCase):
    def test_native_cancellation_reaps_scanner_and_preserves_quarantine(self):
        for ignore_term in (False, True):
            with self.subTest(scanner_ignores_sigterm=ignore_term):
                self.exercise_cancel(ignore_term)

    def exercise_cancel(self, ignore_term):
        with tempfile.TemporaryDirectory(prefix="opener-cancel-") as directory:
            root = Path(directory)
            fake_scanner = root / "fake-scanner.py"
            fake_scanner.write_text(
                "#!/usr/bin/env python3\n"
                "import os, signal, time\n"
                "from pathlib import Path\n"
                "if os.environ.get('IGNORE_SCANNER_TERM') == '1':\n"
                "    signal.signal(signal.SIGTERM, signal.SIG_IGN)\n"
                "Path(os.environ['SCANNER_PID_FILE']).write_text(str(os.getpid()))\n"
                "while True: time.sleep(0.05)\n"
            )
            fake_scanner.chmod(0o700)
            selected = root / "selected.pdf"
            selected.write_bytes(b"%PDF-1.4\nSelected")
            other = root / "queued.pdf"
            other.write_bytes(b"%PDF-1.4\nQueued")
            scanner_pid_file = root / "scanner-pid"
            side_effect = root / "unexpected-open-or-quarantine"
            repo_root = Path(__file__).resolve().parent

            driver = root / "driver.py"
            driver.write_text(f"""
import importlib.util
import pathlib
import sys
sys.path.insert(0, {str(repo_root)!r})
spec = importlib.util.spec_from_file_location("scan_gate", {str(repo_root / "scan-and-open.py")!r})
gate = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = gate
spec.loader.exec_module(gate)
gate.scanner_path = lambda: {str(fake_scanner)!r}
gate.check_database = lambda: None
gate.record_scan_destination = lambda _: None
gate.CACHE_DB = pathlib.Path({str(root / "cache.sqlite3")!r})
gate.remove_quarantine = lambda _: pathlib.Path({str(side_effect)!r}).write_text("quarantine removed")
gate.launch_clean_file = lambda _: pathlib.Path({str(side_effect)!r}).write_text("file opened")
sys.exit(gate.main([{str(selected)!r}, {str(other)!r}]))
""")
            environment = os.environ.copy()
            environment["PDF_MAGIC_NATIVE_CANCEL"] = "1"
            environment["SCANNER_PID_FILE"] = str(scanner_pid_file)
            environment["IGNORE_SCANNER_TERM"] = "1" if ignore_term else "0"
            worker = subprocess.Popen(
                [sys.executable, str(driver)], env=environment,
                stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True
            )
            scanner_pid = None
            try:
                deadline = time.monotonic() + 10
                while time.monotonic() < deadline:
                    if scanner_pid_file.exists():
                        scanner_pid = int(scanner_pid_file.read_text())
                        break
                    if worker.poll() is not None:
                        self.fail("Scan gate exited before starting the scanner")
                    time.sleep(0.05)
                self.assertIsNotNone(scanner_pid, "Test scanner never started")

                worker.send_signal(signal.SIGTERM)
                stdout, stderr = worker.communicate(timeout=10)
                self.assertNotEqual(worker.returncode, 0)
                self.assertIn("cancelled", stderr.lower())
                self.assertFalse(side_effect.exists(), "Cancellation must not open or clear quarantine")
                deadline = time.monotonic() + 3
                while time.monotonic() < deadline:
                    try:
                        os.kill(scanner_pid, 0)
                    except ProcessLookupError:
                        break
                    time.sleep(0.05)
                else:
                    self.fail("Scanner subprocess survived cancellation")
            finally:
                if worker.poll() is None:
                    worker.kill()
                    worker.communicate(timeout=5)
                if scanner_pid is not None:
                    try:
                        os.kill(scanner_pid, signal.SIGKILL)
                    except ProcessLookupError:
                        pass


if __name__ == "__main__":
    unittest.main()
