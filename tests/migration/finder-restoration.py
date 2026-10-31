#!/usr/bin/env python3
"""opener-0945: opt-in and non-destructive Finder action restoration."""

import os
from pathlib import Path
import plistlib
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from restore_finder_quick_action import FIXED_COMMAND, restore_finder_action, RestorationRefused


class FinderRestorationTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="finder-restore-0945-")
        self.addCleanup(temporary.cleanup)
        self.home = Path(temporary.name)
        self.directory = self.home / "Library/Services/Allow and Open.workflow/Contents"
        self.directory.mkdir(parents=True)
        self.workflow = self.directory / "document.wflow"
        self.backup = self.directory / "document.wflow.before-brave"
        self.original = {
            "actions": [
                {"action": {"BundleIdentifier": "com.apple.RunShellScript",
                            "ActionParameters": {
                                "COMMAND_STRING": "echo original user action\n",
                                "shell": "/bin/zsh", "inputMethod": 0,
                                "customSetting": "keep original",
                            }}},
                {"action": {"BundleIdentifier": "example.unrelated",
                            "ActionParameters": {"keep": "untouched"}}},
            ],
            "preferences": ["do not discard"],
        }
        self.backup.write_bytes(plistlib.dumps(self.original, fmt=plistlib.FMT_BINARY))
        managed = plistlib.loads(self.backup.read_bytes())
        params = managed["actions"][0]["action"]["ActionParameters"]
        params.update(COMMAND_STRING=FIXED_COMMAND, inputMethod=1, shell="/bin/bash")
        self.workflow.write_bytes(plistlib.dumps(managed))
        self.managed_bytes = self.workflow.read_bytes()
        self.backup_bytes = self.backup.read_bytes()

    def cli(self, *options):
        return subprocess.run(
            [sys.executable, str(ROOT / "restore_finder_quick_action.py"),
             "--home", str(self.home), *options],
            text=True, capture_output=True, timeout=5
        )

    def test_inspection_is_read_only_and_restoration_is_opt_in(self):
        inode = self.workflow.stat().st_ino
        result = self.cli()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("--restore", result.stdout)
        self.assertEqual(self.workflow.read_bytes(), self.managed_bytes)
        self.assertEqual(self.workflow.stat().st_ino, inode)
        self.assertEqual(self.backup.read_bytes(), self.backup_bytes)

    def test_restore_exact_original_binary_bytes_and_keep_backup(self):
        os.chmod(self.workflow, 0o640)
        result = self.cli("--restore")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.workflow.read_bytes(), self.backup_bytes)
        self.assertEqual(self.backup.read_bytes(), self.backup_bytes)
        self.assertEqual(self.workflow.stat().st_mode & 0o777, 0o640)
        self.assertIn("may not use", result.stdout)

    def test_repeated_restore_is_non_destructive(self):
        self.assertEqual(self.cli("--restore").returncode, 0)
        inode = self.workflow.stat().st_ino
        self.assertEqual(self.cli("--restore").returncode, 0)
        self.assertEqual(self.workflow.stat().st_ino, inode)
        self.assertEqual(self.workflow.read_bytes(), self.backup_bytes)

    def test_custom_shell_and_unrelated_settings_are_never_clobbered(self):
        for mutate in ("command", "other"):
            with self.subTest(mutate=mutate):
                managed = plistlib.loads(self.managed_bytes)
                if mutate == "command":
                    managed["actions"][0]["action"]["ActionParameters"]["COMMAND_STRING"] = "echo custom\n"
                else:
                    managed["preferences"].append("new customization")
                altered = plistlib.dumps(managed)
                self.workflow.write_bytes(altered)
                self.assertNotEqual(self.cli("--restore").returncode, 0)
                self.assertEqual(self.workflow.read_bytes(), altered)
                self.assertEqual(self.backup.read_bytes(), self.backup_bytes)

    def test_missing_or_invalid_backup_is_rejected(self):
        self.backup.unlink()
        self.assertNotEqual(self.cli("--restore").returncode, 0)
        self.assertEqual(self.workflow.read_bytes(), self.managed_bytes)
        self.backup.write_bytes(b"not a plist")
        self.assertNotEqual(self.cli("--restore").returncode, 0)
        self.assertEqual(self.workflow.read_bytes(), self.managed_bytes)

    def test_restore_missing_current_action_without_overwriting_backup(self):
        self.workflow.unlink()
        self.assertEqual(self.cli("--restore").returncode, 0)
        self.assertEqual(self.workflow.read_bytes(), self.backup_bytes)
        self.assertEqual(self.backup.read_bytes(), self.backup_bytes)

    def test_symlinks_to_current_backup_and_ancestor_are_rejected(self):
        external = self.home / "external-wflow"
        external.write_bytes(b"do not change")
        self.workflow.unlink()
        self.workflow.symlink_to(external)
        self.assertNotEqual(self.cli("--restore").returncode, 0)
        self.assertEqual(external.read_bytes(), b"do not change")
        self.workflow.unlink()
        self.workflow.write_bytes(self.managed_bytes)
        self.backup.unlink()
        self.backup.symlink_to(external)
        self.assertNotEqual(self.cli("--restore").returncode, 0)
        self.assertEqual(self.workflow.read_bytes(), self.managed_bytes)
        self.backup.unlink()
        self.backup.write_bytes(self.backup_bytes)

        target = self.directory.parent
        renamed = target.with_name("saved-workflow")
        target.rename(renamed)
        target.symlink_to(renamed)
        self.assertNotEqual(self.cli("--restore").returncode, 0)
        self.assertEqual((renamed / "Contents/document.wflow").read_bytes(), self.managed_bytes)

    def test_hardlinked_backup_is_rejected(self):
        shared = self.home / "another-link"
        os.link(self.backup, shared)
        self.assertNotEqual(self.cli("--restore").returncode, 0)
        self.assertEqual(self.workflow.read_bytes(), self.managed_bytes)

    def test_invalid_managed_workflow_is_never_replaced(self):
        self.workflow.write_bytes(b"corrupt")
        self.assertNotEqual(self.cli("--restore").returncode, 0)
        self.assertEqual(self.workflow.read_bytes(), b"corrupt")

    def test_public_function_dry_run_does_not_change_files(self):
        self.assertIn("--restore", restore_finder_action(self.home))
        self.assertEqual(self.workflow.read_bytes(), self.managed_bytes)
        self.assertEqual(self.backup.read_bytes(), self.backup_bytes)
        with self.assertRaises(RestorationRefused):
            restore_finder_action(self.home / "missing", restore=True)


if __name__ == "__main__":
    unittest.main()
