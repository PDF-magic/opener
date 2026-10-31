#!/usr/bin/env python3
"""Regression coverage for read-only Finder Quick Action migration discovery."""

import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from existing_finder_quick_action import detect_existing_finder_quick_action


class ExistingFinderQuickActionTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="opener-finder-migration-")
        self.addCleanup(temporary.cleanup)
        self.home = Path(temporary.name)
        self.contents = self.home / "Library/Services/Allow and Open.workflow/Contents"
        self.workflow = self.contents / "document.wflow"
        self.backup = self.contents / "document.wflow.before-brave"

    def state(self):
        return detect_existing_finder_quick_action(self.home)

    def test_fresh_install_detects_neither_artifact(self):
        self.assertEqual(self.state(), {
            "finder_quick_action": "missing",
            "finder_quick_action_backup": "missing",
        })
        self.assertEqual(list(self.home.iterdir()), [])

    def test_existing_action_and_backup_detected_independently(self):
        self.contents.mkdir(parents=True)
        original = b"original workflow, including user's customizations\x00"
        preserved = b"legacy backed-up workflow\x01"
        self.workflow.write_bytes(original)
        self.assertEqual(self.state(), {
            "finder_quick_action": "present",
            "finder_quick_action_backup": "missing",
        })
        self.backup.write_bytes(preserved)
        self.assertEqual(self.state(), {
            "finder_quick_action": "present",
            "finder_quick_action_backup": "present",
        })
        self.workflow.unlink()
        self.assertEqual(self.state(), {
            "finder_quick_action": "missing",
            "finder_quick_action_backup": "present",
        })
        self.assertEqual(self.backup.read_bytes(), preserved)

    def test_existing_backup_remains_untouched_across_repeated_detection(self):
        self.contents.mkdir(parents=True)
        original = b"user configured workflow"
        backup = b"unaltered historical backup"
        self.workflow.write_bytes(original)
        self.backup.write_bytes(backup)
        for _ in range(3):
            self.assertEqual(self.state()["finder_quick_action_backup"], "present")
        self.assertEqual(self.workflow.read_bytes(), original)
        self.assertEqual(self.backup.read_bytes(), backup)

    def test_symlinks_and_unexpected_file_types_are_not_treated_as_installed(self):
        self.contents.mkdir(parents=True)
        elsewhere = self.home / "external"
        elsewhere.write_bytes(b"outside user file")
        self.workflow.symlink_to(elsewhere)
        self.backup.mkdir()
        self.assertEqual(self.state(), {
            "finder_quick_action": "unsafe",
            "finder_quick_action_backup": "unsafe",
        })
        self.assertEqual(elsewhere.read_bytes(), b"outside user file")
        self.workflow.unlink()
        self.backup.rmdir()
        self.contents.rmdir()
        (self.home / "Library/Services/Allow and Open.workflow/Contents").symlink_to(self.home)
        self.assertEqual(self.state(), {
            "finder_quick_action": "unsafe",
            "finder_quick_action_backup": "unsafe",
        })

    def test_cli_prints_only_states_not_private_paths(self):
        self.contents.mkdir(parents=True)
        self.backup.write_bytes(b"backup")
        result = subprocess.run(
            [sys.executable, str(ROOT / "existing_finder_quick_action.py"), "--home", str(self.home)],
            capture_output=True, text=True, timeout=5, check=True,
        )
        self.assertEqual(json.loads(result.stdout), self.state())
        self.assertNotIn(str(self.home), result.stdout)
        self.assertFalse(result.stderr)


if __name__ == "__main__":
    unittest.main()
