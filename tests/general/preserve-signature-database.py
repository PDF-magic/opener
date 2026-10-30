#!/usr/bin/env python3
"""opener-0385: failed FreshClam runs cannot replace previously usable signatures."""
import os
from pathlib import Path
import subprocess
import tempfile
import time
import unittest

ROOT = Path(__file__).resolve().parent
CANDIDATES = "/opt/homebrew/bin/freshclam /usr/local/bin/freshclam /usr/local/clamav/bin/freshclam"

FAKE = """#!/bin/bash
set -euo pipefail
stage=""
for argument in "$@"; do
  case "$argument" in --datadir=*) stage="${argument#--datadir=}" ;; esac
done
[ -n "$stage" ] && [ -d "$stage" ] || exit 92
if [ -n "${FAKE_STARTED:-}" ]; then
  printf 'started\\n' > "$FAKE_STARTED"
fi
if [ -n "${FAKE_DELAY:-}" ]; then
  sleep "$FAKE_DELAY"
fi
printf 'new main database\\n' > "$stage/main.cvd"
printf 'new daily database\\n' > "$stage/daily.cld"
if [ "${FAKE_DROP_DAILY:-0}" = 1 ]; then
  /bin/rm "$stage/daily.cld"
fi
exit "${FAKE_EXIT:-0}"
"""


class PreserveSignatureDatabaseTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory(prefix="safe-clamav-update-")
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        self.home = self.root / "home"
        self.install = self.home / "Library/Application Support/Studio/allow-and-open"
        self.signatures = self.install / "signatures"
        self.signatures.mkdir(parents=True)
        self.fake = self.root / "fake-freshclam"
        self.fake.write_text(FAKE)
        self.fake.chmod(0o700)
        script = (ROOT / "update-malware-signatures.sh").read_text()
        self.assertIn(CANDIDATES, script)
        self.script = self.root / "update.sh"
        # Synthetic update tests bypass only the separately tested ClamAV
        # stage-load probe in their disposable updater copy.
        first = script.index("# BEGIN staged database verification (opener-0386)")
        last = script.index("# END staged database verification (opener-0386)") + len("# END staged database verification (opener-0386)")
        script = script[:first] + script[last:]
        self.script.write_text(script.replace(CANDIDATES, str(self.fake)))
        (self.signatures / "main.cvd").write_bytes(b"usable main database\n")
        (self.signatures / "daily.cld").write_bytes(b"usable daily database\n")
        (self.signatures / "last-successful-update").write_text("1700000000\n")
        (self.signatures / "custom.ndb").write_bytes(b"user signatures\n")
        (self.install / "freshclam.conf").write_text(
            'DatabaseDirectory "' + str(self.signatures) + '"\n'
        )
        self.original = {
            p.name: p.read_bytes()
            for p in self.signatures.iterdir() if p.is_file()
        }

    def invoke(self, code=0, **extra):
        env = dict(os.environ, HOME=str(self.home), FAKE_EXIT=str(code))
        env.update({k: str(v) for k, v in extra.items()})
        return subprocess.run(
            ["bash", str(self.script)], env=env,
            capture_output=True, text=True, timeout=15,
        )

    def assert_unchanged(self):
        for name, data in self.original.items():
            with self.subTest(name=name):
                self.assertEqual((self.signatures / name).read_bytes(), data)

    def assert_no_work_dirs(self):
        self.assertEqual(list(self.install.glob(".signature-stage.*")), [])
        self.assertEqual(list(self.install.glob(".signature-backup.*")), [])
        self.assertFalse((self.install / ".signature-update-lock").exists())

    def test_failed_freshclam_does_not_modify_previous_usable_databases(self):
        original_inode = self.signatures.stat().st_ino
        result = self.invoke(23)
        self.assertEqual(result.returncode, 23, result.stderr)
        self.assertEqual(self.signatures.stat().st_ino, original_inode)
        self.assert_unchanged()
        self.assertTrue((self.signatures / "last-attempted-update").is_file())
        self.assert_no_work_dirs()

    def test_success_publishes_new_databases_and_preserves_custom_data(self):
        result = self.invoke()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual((self.signatures / "main.cvd").read_bytes(), b"new main database\n")
        self.assertEqual((self.signatures / "daily.cld").read_bytes(), b"new daily database\n")
        self.assertEqual((self.signatures / "custom.ndb").read_bytes(),
                         self.original["custom.ndb"])
        self.assertGreater(int((self.signatures / "last-successful-update").read_text()), 1700000000)
        self.assert_no_work_dirs()

    def test_missing_updater_leaves_database_and_last_success_intact(self):
        self.fake.unlink()
        result = self.invoke()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("unavailable", result.stderr)
        self.assert_unchanged()
        self.assert_no_work_dirs()

    def test_zero_exit_with_missing_previously_required_database_is_rejected(self):
        result = self.invoke(FAKE_DROP_DAILY=1)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("incomplete", result.stderr)
        self.assert_unchanged()
        self.assert_no_work_dirs()

    def test_linked_database_is_rejected_without_following_it(self):
        (self.signatures / "main.cvd").unlink()
        private = self.root / "private-file"
        private.write_bytes(b"outside database")
        (self.signatures / "main.cvd").symlink_to(private)
        result = self.invoke()
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(private.read_bytes(), b"outside database")
        self.assertTrue((self.signatures / "main.cvd").is_symlink())
        self.assert_no_work_dirs()

    def test_overlapping_runs_cannot_replace_newer_update(self):
        started = self.root / "started"
        env = dict(os.environ, HOME=str(self.home), FAKE_EXIT="0",
                   FAKE_DELAY="1.5", FAKE_STARTED=str(started))
        first = subprocess.Popen(["bash", str(self.script)], env=env,
                                 stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                 text=True)
        self.addCleanup(lambda: first.kill() if first.poll() is None else None)
        deadline = time.monotonic() + 5
        while not started.exists() and time.monotonic() < deadline:
            if first.poll() is not None:
                break
            time.sleep(0.02)
        self.assertTrue(started.exists(), "First update never reached FreshClam")
        attempt = self.signatures / "last-attempted-update"
        original_stamp_inode = attempt.stat().st_ino
        second = self.invoke()
        self.assertNotEqual(second.returncode, 0)
        self.assertIn("Another signature update", second.stderr)
        # The loser must be stopped at lock acquisition, before it can
        # rewrite shared update metadata or touch the signature database.
        self.assertEqual(attempt.stat().st_ino, original_stamp_inode)
        out, err = first.communicate(timeout=10)
        self.assertEqual(first.returncode, 0, (out, err))
        self.assertEqual((self.signatures / "main.cvd").read_bytes(), b"new main database\n")
        self.assert_no_work_dirs()

    def test_scan_gate_remains_independent_and_ci_runs_regressions(self):
        source = (ROOT / "scan-and-open.py").read_text()
        self.assertIn("MAX_DATABASE_AGE = 48 * 60 * 60", source)
        self.assertIn("check_database()", source)
        ci = (ROOT / ".github/workflows/ci.yml").read_text()
        self.assertIn("python3 scripts/run-test.py tests/general/preserve-signature-database.py -v", ci)
        self.assertIn("bash -n install-allow-and-open.sh", ci)


if __name__ == "__main__":
    unittest.main()
