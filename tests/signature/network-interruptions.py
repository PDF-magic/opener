#!/usr/bin/env python3
"""opener-0389: bounded recovery and fail-closed interruption of FreshClam."""
import os
from pathlib import Path
import signal
import subprocess
import tempfile
import time
import unittest

ROOT = Path(__file__).resolve().parent
CANDIDATES = "/opt/homebrew/bin/freshclam /usr/local/bin/freshclam /usr/local/clamav/bin/freshclam"
FAKE = r"""#!/bin/bash
set -euo pipefail
count=0
if [ -f "$FAKE_COUNT" ]; then
  count="$(cat "$FAKE_COUNT")"
fi
count=$((count + 1))
printf '%s\n' "$count" > "$FAKE_COUNT"
case "$FAKE_MODE" in
  recover) if [ "$count" -eq 1 ]; then exit 52; fi ;;
  offline) exit 52 ;;
  signaled) exit 143 ;;
  block)
    printf '%s\n' "$$" > "$FAKE_CHILD_PID"
    trap 'exit 143' TERM
    while [ ! -f "$FAKE_RELEASE" ]; do /bin/sleep 0.05; done
    ;;
  clean) ;;
  *) exit 99 ;;
esac
exit 0
"""


class NetworkInterruptionTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory(prefix="clamav-network-interruption-")
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        self.home = self.root / "home"
        self.signatures = self.home / "Library/Application Support/Studio/allow-and-open/signatures"
        self.signatures.mkdir(parents=True)
        self.success = self.signatures / "last-successful-update"
        self.success.write_text("1700000000\n")
        self.counter = self.root / "counter"
        self.child = self.root / "child-pid"
        self.release = self.root / "release"
        self.fake = self.root / "fake-freshclam"
        self.fake.write_text(FAKE)
        self.fake.chmod(0o700)
        script = (ROOT / "update-malware-signatures.sh").read_text()
        self.assertIn(CANDIDATES, script)
        self.script = self.root / "updater.sh"
        # Synthetic update tests bypass only the separately tested ClamAV
        # stage-load probe in their disposable updater copy.
        first = script.index("# BEGIN staged database verification (opener-0386)")
        last = script.index("# END staged database verification (opener-0386)") + len("# END staged database verification (opener-0386)")
        script = script[:first] + script[last:]
        self.script.write_text(script.replace(CANDIDATES, str(self.fake)))

    def environment(self, mode):
        return dict(os.environ, HOME=str(self.home), FAKE_MODE=mode,
                    FAKE_COUNT=str(self.counter), FAKE_CHILD_PID=str(self.child),
                    FAKE_RELEASE=str(self.release))

    def invoke(self, mode):
        return subprocess.run(["bash", str(self.script)],
                              env=self.environment(mode),
                              capture_output=True, text=True, timeout=12)

    def attempts(self):
        return int(self.counter.read_text())

    def assert_clean_progress(self):
        self.assertFalse((self.signatures / "update-in-progress").exists())
        self.assertEqual(list(self.signatures.glob(".update-in-progress.*")), [])

    def test_temporary_connection_failure_recovers_once(self):
        result = self.invoke("recover")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.attempts(), 2)
        self.assertGreater(int(self.success.read_text()), 1700000000)
        self.assertFalse((self.signatures / "last-failed-update").exists())
        self.assertTrue((self.signatures / "last-attempted-update").exists())
        self.assert_clean_progress()

    def test_persistent_disconnection_is_bounded_and_fails_closed(self):
        result = self.invoke("offline")
        self.assertEqual(result.returncode, 52)
        self.assertEqual(self.attempts(), 2, "Never enter an unlimited retry loop")
        self.assertEqual(self.success.read_text(), "1700000000\n")
        self.assert_clean_progress()
        marker = (self.signatures / "last-failed-update").read_text().strip().split()
        self.assertEqual(len(marker), 2)
        self.assertEqual(marker[1], "freshclam-error")
        self.assertNotIn(str(self.home), " ".join(marker))

    def test_freshclam_terminated_by_signal_is_not_retried(self):
        result = self.invoke("signaled")
        self.assertEqual(result.returncode, 143)
        self.assertEqual(self.attempts(), 1)
        self.assertEqual(self.success.read_text(), "1700000000\n")
        self.assert_clean_progress()

    def test_stopped_updater_terminates_child_without_advancing_success(self):
        process = subprocess.Popen(["bash", str(self.script)],
                                   env=self.environment("block"),
                                   stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        self.addCleanup(lambda: process.kill() if process.poll() is None else None)
        deadline = time.monotonic() + 7
        while not self.child.exists() and time.monotonic() < deadline:
            if process.poll() is not None:
                self.fail("Updater exited before FreshClam started")
            time.sleep(0.03)
        self.assertTrue(self.child.is_file(), "FreshClam never started")
        child_pid = int(self.child.read_text())
        self.assertNotEqual(child_pid, process.pid)
        process.send_signal(signal.SIGTERM)
        output, error = process.communicate(timeout=7)
        self.assertEqual(process.returncode, 143, (output, error))
        self.assertEqual(self.attempts(), 1)
        self.assertEqual(self.success.read_text(), "1700000000\n")
        self.assert_clean_progress()
        marker = (self.signatures / "last-failed-update").read_text()
        self.assertIn("freshclam-error", marker)
        # The child has been reaped by the wrapper; no deferred write can
        # advance the success stamp after an interrupted network operation.
        with self.assertRaises(ProcessLookupError):
            os.kill(child_pid, 0)

    def test_following_scheduled_run_recovers_normally(self):
        self.assertEqual(self.invoke("offline").returncode, 52)
        self.counter.unlink()
        self.assertEqual(self.invoke("clean").returncode, 0)
        self.assertGreater(int(self.success.read_text()), 1700000000)
        self.assert_clean_progress()

    def test_scanner_policy_and_user_update_settings_are_unchanged(self):
        script = (ROOT / "update-malware-signatures.sh").read_text()
        self.assertIn("run_freshclam_with_network_recovery", script)
        self.assertIn('trap cleanup EXIT', script)
        self.assertIn('cleanup_progress', script)
        self.assertIn('"$updater" --config-file=', script.replace('"$candidate" --config-file=', '"$updater" --config-file='))
        self.assertIn('trap \'interrupt_update 143\' TERM', script)
        self.assertNotIn("curl ", script)
        self.assertNotIn("wget ", script)
        self.assertNotIn("last-successful-update.new", script.split("run_freshclam_with_network_recovery() {")[1].split("for candidate in")[0])
        scanner = (ROOT / "scan-and-open.py").read_text()
        self.assertIn("MAX_DATABASE_AGE = 48 * 60 * 60", scanner)
        self.assertNotIn("run_freshclam_with_network_recovery", scanner)
        installer = (ROOT / "install-allow-and-open.sh").read_text()
        self.assertIn("'StartInterval': 14400", installer)
        self.assertIn("'RunAtLoad': True", installer)
        ci = (ROOT / ".github/workflows/ci.yml").read_text()
        self.assertIn("python3 test-signature-network-interruptions.py -v", ci)


if __name__ == "__main__":
    unittest.main()
