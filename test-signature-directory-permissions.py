#!/usr/bin/env python3
"""opener-0394: permission errors cannot activate or destroy ClamAV signatures."""
from contextlib import contextmanager
import os
from pathlib import Path
import stat
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parent
FRESHCLAM_CANDIDATES = (
    "/opt/homebrew/bin/freshclam /usr/local/bin/freshclam "
    "/usr/local/clamav/bin/freshclam"
)
FAKE_FRESHCLAM = """#!/bin/bash
set -euo pipefail
printf 'invoked\\n' > "$FAKE_STARTED"
exit 143
"""


class SignatureDirectoryPermissionTests(unittest.TestCase):
    def setUp(self):
        if os.geteuid() == 0:
            self.skipTest("Real permission-denial tests require an unprivileged user")

        temp = tempfile.TemporaryDirectory(prefix="signature-permissions-")
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        self.home = self.root / "home"
        self.install = (
            self.home / "Library/Application Support/Studio/allow-and-open"
        )
        self.signatures = self.install / "signatures"
        self.signatures.mkdir(parents=True)
        (self.signatures / "main.cvd").write_bytes(b"old main signatures\n")
        (self.signatures / "daily.cld").write_bytes(b"old daily signatures\n")
        (self.signatures / "custom.ndb").write_bytes(b"custom signature\n")
        (self.signatures / "last-successful-update").write_text("1700000000\n")
        (self.install / "freshclam.conf").write_text("synthetic config\n")
        self.original = {
            file.name: file.read_bytes()
            for file in self.signatures.iterdir()
        }
        self.original_inode = self.signatures.stat().st_ino

        self.started = self.root / "freshclam-started"
        self.fake = self.root / "fake-freshclam"
        self.fake.write_text(FAKE_FRESHCLAM)
        self.fake.chmod(0o700)
        source = (ROOT / "update-malware-signatures.sh").read_text()
        self.assertIn(FRESHCLAM_CANDIDATES, source)
        self.script = self.root / "update.sh"
        self.script.write_text(
            source.replace(FRESHCLAM_CANDIDATES, str(self.fake))
        )

    @contextmanager
    def restricted(self, path, mode):
        original_mode = stat.S_IMODE(path.stat().st_mode)
        path.chmod(mode)
        try:
            self.assertEqual(stat.S_IMODE(path.stat().st_mode), mode)
            yield
        finally:
            path.chmod(original_mode)

    def run_updater(self):
        env = dict(
            os.environ,
            HOME=str(self.home),
            FAKE_STARTED=str(self.started),
        )
        return subprocess.run(
            ["bash", str(self.script)],
            env=env,
            capture_output=True,
            text=True,
            timeout=15,
        )

    def assert_rejected_without_data_loss(self, result):
        self.assertNotEqual(result.returncode, 0, result.stderr)
        self.assertFalse(self.started.exists(), "FreshClam should not run")
        self.assertEqual(self.signatures.stat().st_ino, self.original_inode)
        for name, contents in self.original.items():
            with self.subTest(file=name):
                self.assertEqual((self.signatures / name).read_bytes(), contents)
        self.assertFalse((self.signatures / "update-in-progress").exists())
        self.assertFalse((self.install / ".signature-update-lock").exists())
        self.assertEqual(list(self.install.glob(".signature-stage.*")), [])
        self.assertEqual(list(self.install.glob(".signature-backup.*")), [])
        self.assertEqual(list(self.install.glob(".signature-validation.*")), [])

    def test_fixture_can_reach_updater_when_permissions_are_normal(self):
        result = self.run_updater()
        self.assertEqual(result.returncode, 143, result.stderr)
        self.assertTrue(self.started.is_file(), "Fake updater was not reached")
        self.assertEqual(
            (self.signatures / "last-successful-update").read_bytes(),
            self.original["last-successful-update"],
        )

    def test_read_only_signature_directory_cannot_record_or_publish_update(self):
        with self.restricted(self.signatures, 0o500):
            result = self.run_updater()
        self.assert_rejected_without_data_loss(result)

    def test_unreadable_signature_directory_cannot_be_copied_into_stage(self):
        # Writable/searchable but not listable: metadata can be attempted,
        # yet no unreadable live directory may be promoted.
        with self.restricted(self.signatures, 0o300):
            result = self.run_updater()
        self.assert_rejected_without_data_loss(result)

    def test_inaccessible_signature_directory_fails_closed(self):
        with self.restricted(self.signatures, 0o000):
            result = self.run_updater()
        self.assert_rejected_without_data_loss(result)

    def test_unreadable_database_file_never_reaches_updater(self):
        with self.restricted(self.signatures / "main.cvd", 0o000):
            result = self.run_updater()
        self.assert_rejected_without_data_loss(result)

    def test_unwritable_install_directory_cannot_create_update_lock(self):
        with self.restricted(self.install, 0o500):
            result = self.run_updater()
        self.assert_rejected_without_data_loss(result)

    def test_ci_runs_real_permission_denials_on_linux_and_macos(self):
        workflow = (ROOT / ".github/workflows/ci.yml").read_text()
        self.assertEqual(
            workflow.count("python3 test-signature-directory-permissions.py -v"),
            2,
        )
        script = (ROOT / "update-malware-signatures.sh").read_text()
        self.assertIn('trap cleanup EXIT', script)
        self.assertIn('run_freshclam_with_network_recovery "$updater"', script)
        self.assertIn('check_incomplete_downloads "$stage_dir"', script)
        self.assertIn('if ! scan_output=', script)


if __name__ == "__main__":
    unittest.main()
