#!/usr/bin/env python3
"""opener-0378: separate safe detection of FreshClam attempts and successes."""
import datetime
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location("signature_update_status", ROOT / "signature_update_status.py")
status = importlib.util.module_from_spec(spec)
spec.loader.exec_module(status)


class SignatureUpdateTimeTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="signature-update-times-")
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.home = self.root / "home"
        self.signatures = (self.home / "Library/Application Support/Studio/allow-and-open/signatures")
        self.signatures.mkdir(parents=True)
        self.installed = self.signatures.parent
        (self.installed / "freshclam.conf").write_text("synthetic config\n")
        self.fake = self.root / "fake-freshclam"
        self.fake.write_text("#!/bin/sh\nprintf called > \"$FAKE_CALLED\"\nexit \"$FAKE_EXIT\"\n")
        self.fake.chmod(0o700)
        # Adapt the *test copy* only. Neither production paths nor installed
        # scanners, signature databases or user files are touched.
        original = (ROOT / "update-malware-signatures.sh").read_text()
        names = "/opt/homebrew/bin/freshclam /usr/local/bin/freshclam /usr/local/clamav/bin/freshclam"
        self.assertIn(names, original)
        self.script = self.root / "test-update.sh"
        # Synthetic update tests bypass only the separately tested ClamAV
        # stage-load probe in their disposable updater copy.
        first = original.index("# BEGIN staged database verification (opener-0386)")
        last = original.index("# END staged database verification (opener-0386)") + len("# END staged database verification (opener-0386)")
        original = original[:first] + original[last:]
        self.script.write_text(original.replace(names, str(self.fake)))
        self.called = self.root / "called"

    def invoke(self, exit_code=0, *, missing=False):
        if missing and self.fake.exists():
            self.fake.unlink()
        env = dict(os.environ, HOME=str(self.home), FAKE_EXIT=str(exit_code),
                   FAKE_CALLED=str(self.called))
        return subprocess.run(["bash", str(self.script)], env=env,
                              capture_output=True, text=True, timeout=10)

    def test_initial_missing_status_is_unknown(self):
        self.assertEqual(status.read_update_status(self.signatures), {
            "lastAttemptedUpdateUtc": None, "lastSuccessfulUpdateUtc": None,
        })

    def test_success_records_attempt_and_success_without_guessing_result(self):
        result = self.invoke()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue(self.called.exists())
        report = status.read_update_status(self.signatures)
        self.assertIsNotNone(report["lastAttemptedUpdateUtc"])
        self.assertIsNotNone(report["lastSuccessfulUpdateUtc"])
        for field in report.values():
            self.assertTrue(field.endswith("Z"))
        attempt = int((self.signatures / status.ATTEMPT_STAMP).read_text())
        success = int((self.signatures / status.SUCCESS_STAMP).read_text())
        self.assertGreaterEqual(success, attempt)
        # The synthetic updater runs within a ten-second subprocess timeout.
        self.assertLessEqual(success - attempt, 10)

    def test_failed_update_records_attempt_without_modifying_last_success(self):
        self.assertEqual(self.invoke().returncode, 0)
        last_success = (self.signatures / status.SUCCESS_STAMP)
        previous = str(int(time.time()) - 1800) + "\n"
        last_success.write_text(previous)
        result = self.invoke(13)
        self.assertEqual(result.returncode, 13)
        self.assertEqual(last_success.read_text(), previous)
        self.assertIsNotNone(status.read_update_status(self.signatures)["lastAttemptedUpdateUtc"])
        self.assertIsNotNone(status.read_update_status(self.signatures)["lastSuccessfulUpdateUtc"])

    def test_missing_updater_still_records_attempt_but_not_success(self):
        result = self.invoke(missing=True)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("updater is unavailable", result.stderr)
        report = status.read_update_status(self.signatures)
        self.assertIsNotNone(report["lastAttemptedUpdateUtc"])
        self.assertIsNone(report["lastSuccessfulUpdateUtc"])

    def test_invalid_stamp_contents_do_not_become_fake_times(self):
        marker = self.signatures / status.ATTEMPT_STAMP
        now = 1_700_000_000
        for value in ("", "nan", "inf", "-1", "0", "junk", "2026-10-28T12:00Z",
                      str(now + 1), "1" * 60, "1\n2", ".5"):
            with self.subTest(value=value):
                marker.write_text(value)
                self.assertIsNone(status.read_update_time(marker, now=now))
        marker.write_text("1700000000\n")
        self.assertEqual(status.read_update_time(marker, now=now),
                         datetime.datetime.fromtimestamp(now, datetime.timezone.utc))
        marker.write_text("1699999999.5\n")
        self.assertIsNotNone(status.read_update_time(marker, now=now))

    def test_symlinks_and_nonregular_files_are_not_read(self):
        marker = self.signatures / status.SUCCESS_STAMP
        outside = self.root / "outside-file"
        outside.write_text("1700000000\n")
        marker.symlink_to(outside)
        self.assertIsNone(status.read_update_time(marker, now=1_700_000_001))
        marker.unlink()
        marker.mkdir()
        self.assertIsNone(status.read_update_time(marker, now=1_700_000_001))

    def test_scan_gate_installation_and_agent_are_not_changed(self):
        gate = (ROOT / "scan-and-open.py").read_text()
        self.assertNotIn("signature_update_status", gate)
        self.assertIn("MAX_DATABASE_AGE = 48 * 60 * 60", gate)
        installer = (ROOT / "install-allow-and-open.sh").read_text()
        self.assertIn('"$script_dir/signature_update_status.py"', installer)
        self.assertIn("'Label': 'local.studio.pdf-malware-signatures'", installer)
        self.assertIn("'StartInterval': 14400", installer)
        self.assertIn("'RunAtLoad': True", installer)
        ci = (ROOT / ".github/workflows/ci.yml").read_text()
        self.assertIn("python3 tests/signature/update-times.py -v", ci)


if __name__ == "__main__":
    unittest.main()
