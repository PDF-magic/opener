#!/usr/bin/env python3
"""opener-0395: recover a LaunchAgent update after an interrupted system boot."""
import os
from pathlib import Path
import re
import signal
import subprocess
import sys
import tempfile
import time
import unittest

ROOT = Path(__file__).resolve().parent
CANDIDATES = "/opt/homebrew/bin/freshclam /usr/local/bin/freshclam /usr/local/clamav/bin/freshclam"
FAKE = r"""#!/bin/bash
set -euo pipefail
stage=""
for argument in "$@"; do
  case "$argument" in --datadir=*) stage="${argument#--datadir=}" ;; esac
done
[ -d "$stage" ] || exit 91
printf 'called\n' >> "$FAKE_CALLS"
if [ "${FAKE_HOLD:-0}" = "1" ]; then
  printf '%s\n' "$$" > "$FAKE_READY"
  while true; do /bin/sleep 0.1; done
fi
printf 'new main database\n' > "$stage/main.cvd"
printf 'new daily database\n' > "$stage/daily.cld"
"""


def boot_time():
    if sys.platform == "darwin":
        output = subprocess.check_output(
            ["/usr/sbin/sysctl", "-n", "kern.boottime"], text=True,
        )
        match = re.search(r"\bsec\s*=\s*(\d+)", output)
        if match is None:
            raise AssertionError("Unable to identify macOS boot time")
        return int(match.group(1))
    with open("/proc/stat", encoding="ascii") as source:
        for line in source:
            match = re.fullmatch(r"btime\s+(\d+)\s*", line)
            if match:
                return int(match.group(1))
    raise AssertionError("Unable to identify test runner boot time")


class SignatureAgentRestartTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory(prefix="signature-agent-restart-")
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        self.home = self.root / "home"
        self.install = self.home / "Library/Application Support/Studio/allow-and-open"
        self.signatures = self.install / "signatures"
        self.signatures.mkdir(parents=True)
        self.lock = self.install / ".signature-update-lock"
        self.success = self.signatures / "last-successful-update"
        self.success.write_text("1700000000\n")
        (self.signatures / "main.cvd").write_bytes(b"original main database\n")
        (self.signatures / "daily.cld").write_bytes(b"original daily database\n")
        self.config = self.install / "freshclam.conf"
        self.config.write_text("CustomMirror local.example\n")
        self.fake = self.root / "fake-freshclam"
        self.fake.write_text(FAKE)
        self.fake.chmod(0o700)
        original = (ROOT / "update-malware-signatures.sh").read_text()
        self.assertIn(CANDIDATES, original)
        # The real ClamAV engine's staged validation is exercised separately.
        # Only the disposable test copy skips that scanner integration probe.
        begin = original.index("# BEGIN staged database verification (opener-0386)")
        end = original.index("# END staged database verification (opener-0386)")
        end += len("# END staged database verification (opener-0386)")
        self.script = self.root / "updater.sh"
        self.script.write_text((original[:begin] + original[end:]).replace(
            CANDIDATES, str(self.fake)))
        self.ready = self.root / "ready"
        self.calls = self.root / "calls"

    def environment(self, *, hold=False):
        return dict(os.environ, HOME=str(self.home),
                    FAKE_HOLD="1" if hold else "0",
                    FAKE_READY=str(self.ready), FAKE_CALLS=str(self.calls))

    def invoke(self):
        return subprocess.run(
            ["bash", str(self.script)], env=self.environment(),
            capture_output=True, text=True, timeout=15,
        )

    def assert_original_database(self):
        self.assertEqual((self.signatures / "main.cvd").read_bytes(),
                         b"original main database\n")
        self.assertEqual((self.signatures / "daily.cld").read_bytes(),
                         b"original daily database\n")
        self.assertEqual(self.success.read_text(), "1700000000\n")

    def test_interrupted_agent_recovers_on_next_login_without_stale_promotion(self):
        previous = subprocess.Popen(
            ["bash", str(self.script)], env=self.environment(hold=True),
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            start_new_session=True,
        )
        self.addCleanup(
            lambda: os.killpg(previous.pid, signal.SIGKILL)
            if previous.poll() is None else None)
        try:
            deadline = time.monotonic() + 8
            while not self.ready.exists() and time.monotonic() < deadline:
                if previous.poll() is not None:
                    self.fail("Simulated updater exited before FreshClam started")
                time.sleep(0.03)
            self.assertTrue(self.ready.exists(), "Updater never acquired lock")
            self.assertTrue(self.lock.is_dir())
            self.assertTrue((self.signatures / "update-in-progress").exists())
            self.assertEqual(len(list(self.install.glob(".signature-stage.*"))), 1)
            self.assert_original_database()

            # A simultaneous manual or scheduled update must not steal the
            # running agent's lock or touch its update metadata.
            attempted = self.signatures / "last-attempted-update"
            attempt_before = attempted.stat().st_ino
            concurrent = self.invoke()
            self.assertNotEqual(concurrent.returncode, 0)
            self.assertIn("Another signature update", concurrent.stderr)
            self.assertEqual(attempted.stat().st_ino, attempt_before)
            self.assertEqual(self.calls.read_text().splitlines(), ["called"])

            # Simulate power loss: no EXIT trap executes, and all updater
            # processes disappear together, leaving the old lock on disk.
            os.killpg(previous.pid, signal.SIGKILL)
            previous.wait(timeout=5)
            self.assertTrue(self.lock.is_dir())
            self.assert_original_database()
            # Give that leftover directory a timestamp from the *previous*
            # boot. This tests boot recovery without rebooting a CI runner.
            before_boot = boot_time() - 5
            os.utime(self.lock, (before_boot, before_boot))
            resumed = self.invoke()
            self.assertEqual(resumed.returncode, 0, resumed.stderr)
            self.assertEqual((self.signatures / "main.cvd").read_bytes(),
                             b"new main database\n")
            self.assertEqual((self.signatures / "daily.cld").read_bytes(),
                             b"new daily database\n")
            self.assertGreater(int(self.success.read_text()), 1700000000)
            self.assertFalse(self.lock.exists())
            self.assertFalse((self.signatures / "update-in-progress").exists())
            self.assertEqual(self.calls.read_text().splitlines(),
                             ["called", "called"])
            self.assertEqual(self.config.read_text(),
                             "CustomMirror local.example\n")
        finally:
            if previous.poll() is None:
                os.killpg(previous.pid, signal.SIGKILL)
                previous.wait(timeout=5)

    def test_same_boot_lock_cannot_be_recovered(self):
        self.lock.mkdir()
        result = self.invoke()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("Another signature update", result.stderr)
        self.assertTrue(self.lock.is_dir())
        self.assertFalse(self.calls.exists())
        self.assert_original_database()

    def test_old_nonempty_lock_fails_closed(self):
        self.lock.mkdir()
        preserved = self.lock / "unrecognized-owner"
        preserved.write_text("do not remove\n")
        old = boot_time() - 5
        os.utime(self.lock, (old, old))
        result = self.invoke()
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(preserved.read_text(), "do not remove\n")
        self.assertFalse(self.calls.exists())
        self.assert_original_database()

    def test_symlinked_lock_is_not_followed(self):
        external = self.root / "other"
        external.mkdir()
        self.lock.symlink_to(external, target_is_directory=True)
        result = self.invoke()
        self.assertNotEqual(result.returncode, 0)
        self.assertTrue(self.lock.is_symlink())
        self.assertTrue(external.is_dir())
        self.assertFalse(self.calls.exists())
        self.assert_original_database()

    def test_launch_agent_startup_and_scanner_policy_remain_intact(self):
        installer = (ROOT / "install-allow-and-open.sh").read_text()
        self.assertIn("'Label': 'local.studio.pdf-malware-signatures'", installer)
        self.assertIn("'RunAtLoad': True", installer)
        self.assertIn("'StartInterval': 14400", installer)
        self.assertIn("'ProgramArguments': ['/bin/bash', str(install_dir / 'update-malware-signatures.sh')]", installer)
        script = (ROOT / "update-malware-signatures.sh").read_text()
        self.assertIn("fcntl.flock(descriptor, fcntl.LOCK_EX)", script)
        self.assertIn("previous.st_mtime >= started", script)
        self.assertIn("os.rmdir(lock_dir)", script)
        self.assertIn('trap cleanup EXIT', script)
        scan = (ROOT / "scan-and-open.py").read_text()
        self.assertIn("MAX_DATABASE_AGE = 48 * 60 * 60", scan)
        ci = (ROOT / ".github/workflows/ci.yml").read_text()
        self.assertIn("python3 scripts/run-test.py tests/signature/agent-restart.py -v", ci)


if __name__ == "__main__":
    unittest.main()
