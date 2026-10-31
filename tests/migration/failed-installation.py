#!/usr/bin/env python3
"""Use disposable fixtures to verify failed migrations preserve working openers."""
import importlib.util
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location(
    "preserve_existing_opener", ROOT / "scripts/preserve_existing_opener.py")
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class FailedInstallationTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="opener-recovery-")
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.install = self.root / "programs"
        self.install.mkdir()
        self.backup = self.root / "backup"
        self.backup.mkdir(mode=0o700)
        self.original = self.install / "scan-and-open.py"
        self.original.write_bytes(b"working scanner\n")
        self.original.chmod(0o700)
        (self.install / "target-app.txt").write_bytes(b"custom browser\n")
        (self.install / "freshclam.conf").write_bytes(b"custom proxy settings\n")

    def test_restore_overwritten_programs_without_changing_user_settings(self):
        before = self.original.stat()
        module.snapshot(self.install, self.backup)
        self.original.write_bytes(b"broken replacement")
        (self.install / "file_launcher.py").write_bytes(b"new helper")
        module.restore(self.install, self.backup)
        self.assertEqual(self.original.read_bytes(), b"working scanner\n")
        self.assertEqual(self.original.stat().st_mode & 0o777, 0o700)
        self.assertEqual(self.original.stat().st_mtime_ns, before.st_mtime_ns)
        self.assertFalse((self.install / "file_launcher.py").exists())
        self.assertEqual((self.install / "target-app.txt").read_bytes(), b"custom browser\n")
        self.assertEqual((self.install / "freshclam.conf").read_bytes(), b"custom proxy settings\n")

    def test_new_install_restores_absence_without_touching_unrelated_files(self):
        self.original.unlink()
        module.snapshot(self.install, self.backup)
        self.original.write_bytes(b"incomplete install")
        module.restore(self.install, self.backup)
        self.assertFalse(self.original.exists())
        self.assertTrue((self.install / "target-app.txt").exists())

    def test_refuse_symlink_and_preserve_external_data(self):
        outside = self.root / "outside"
        outside.write_bytes(b"untouched")
        self.original.unlink()
        self.original.symlink_to(outside)
        with self.assertRaises(ValueError):
            module.snapshot(self.install, self.backup)
        self.assertEqual(outside.read_bytes(), b"untouched")
        self.original.unlink()
        self.original.write_bytes(b"working")
        recovery = self.root / "second"
        recovery.mkdir()
        module.snapshot(self.install, recovery)
        self.original.unlink()
        self.original.symlink_to(outside)
        with self.assertRaises(ValueError):
            module.restore(self.install, recovery)
        self.assertEqual(outside.read_bytes(), b"untouched")
        self.assertTrue((recovery / "scan-and-open.py").exists())

    def test_failed_app_swap_restores_previous_bundle_and_legacy_name(self):
        installer = (ROOT / "install-allow-and-open.sh").read_text()
        extracted = re.search(r"(?ms)^rollback_installation\(\) \{\n.*?^\}", installer)
        self.assertIsNotNone(extracted)
        for legacy in (False, True):
            with self.subTest(legacy=legacy):
                home = self.root / ("legacy" if legacy else "modern")
                app_dir = home / "Applications"
                app_dir.mkdir(parents=True)
                stage = app_dir / ".staged"
                stage.mkdir()
                app = app_dir / "PDF Magic Opener.app"
                app.mkdir()
                (app / "version").write_text("new")
                previous = stage / "previous.app"
                previous.mkdir()
                (previous / "version").write_text("working")
                legacy_app = app_dir / "Open PDFs in Brave.app"
                context = f"""
set -eu
script_dir={str(ROOT)!r}
install_dir={str(self.install)!r}
installed_app={str(app)!r}
legacy_app={str(legacy_app)!r}
bundle_stage_dir={str(stage)!r}
install_snapshot=""
snapshot_ready=0
new_app_installed=1
legacy_was_moved={int(legacy)}
migration_committed=0
{extracted.group(0)}
trap rollback_installation EXIT
exit 9
"""
                completed = subprocess.run(["bash", "-c", context], text=True,
                                           capture_output=True)
                self.assertEqual(completed.returncode, 9, completed.stderr)
                expected = legacy_app if legacy else app
                self.assertEqual((expected / "version").read_text(), "working")
                self.assertFalse((app if legacy else legacy_app).exists())
                self.assertFalse(stage.exists())

    def test_installer_snapshots_before_overwriting_programs_and_defers_legacy_rename(self):
        installer = (ROOT / "install-allow-and-open.sh").read_text()
        self.assertLess(installer.index('preserve_existing_opener.py" snapshot'),
                        installer.index('cp "$script_dir/allow-and-open.sh"'))
        self.assertLess(installer.index('verify_pdf_opener_bundle.py" "$app"'),
                        installer.index("legacy.rename(destination)"))
        self.assertLess(installer.index("legacy.rename(destination)"),
                        installer.index('mv "$app" "$installed_app"'))
        self.assertLess(installer.index('migrate_update_agent.py"'),
                        installer.index("migration_committed=1"))
        self.assertIn('trap rollback_installation EXIT', installer)
        self.assertNotIn('trap cleanup_bundle_stage EXIT', installer)


if __name__ == "__main__":
    unittest.main()
