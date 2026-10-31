#!/usr/bin/env python3
"""opener-0851: never interpolate caller-controlled paths into shell source."""

import os
from pathlib import Path
import plistlib
import subprocess
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[2]
INSTALLER = ROOT / "install-allow-and-open.sh"
FIXED_COMMAND = (
    'export PDF_MAGIC_REQUEST_ORIGIN=finder\n'
    'exec /bin/bash "$HOME/Library/Application Support/Studio/'
    'allow-and-open/allow-and-open.sh" "$@"\n'
)


def finder_installation_script():
    """Exercise the real installer heredoc without running the installer."""
    source = INSTALLER.read_text(encoding="utf-8")
    marker = 'python3 - "$workflow" <<\'PY\'\n'
    assert source.count(marker) == 1, "Finder workflow must take only its plist path"
    return source.split(marker, 1)[1].split("\nPY\n", 1)[0]


class FinderCommandStringSafetyTests(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory(prefix="finder-command-safety-")
        self.addCleanup(directory.cleanup)
        self.root = Path(directory.name)
        self.workflow = self.root / "document.wflow"

    def write_workflow(self, action_count=1):
        actions = [
            {"action": {
                "BundleIdentifier": "com.apple.RunShellScript",
                "ActionParameters": {
                    "COMMAND_STRING": (
                        '/bin/bash "$HOME/Library/Application Support/Studio/'
                        'allow-and-open/allow-and-open.sh" "$@"\n'
                    ),
                    "shell": "/bin/zsh",
                    "inputMethod": 0,
                    "customization": "must-stay",
                },
            }}
            for _ in range(action_count)
        ]
        actions.append({"action": {
            "BundleIdentifier": "example.unrelated",
            "ActionParameters": {"COMMAND_STRING": "preserve unrelated action"},
        }})
        original = {"actions": actions, "otherPreferences": ["untouched"]}
        with self.workflow.open("wb") as stream:
            plistlib.dump(original, stream)
        return original

    def run_workflow_update(self):
        return subprocess.run(
            [sys.executable, "-c", finder_installation_script(), str(self.workflow)],
            capture_output=True, text=True, timeout=5,
        )

    def test_finder_command_is_fixed_and_other_customizations_survive(self):
        original = self.write_workflow()
        updated = self.run_workflow_update()
        self.assertEqual(updated.returncode, 0, updated.stderr)
        with self.workflow.open("rb") as stream:
            current = plistlib.load(stream)
        command = current["actions"][0]["action"]["ActionParameters"]
        self.assertEqual(command["COMMAND_STRING"], FIXED_COMMAND)
        self.assertEqual(command["inputMethod"], 1)
        self.assertEqual(command["shell"], "/bin/bash")
        self.assertEqual(command["customization"], "must-stay")
        self.assertEqual(current["actions"][1], original["actions"][1])
        self.assertEqual(current["otherPreferences"], original["otherPreferences"])
        with self.workflow.with_name("document.wflow.before-brave").open("rb") as stream:
            self.assertEqual(plistlib.load(stream), original)

    def test_shell_metacharacters_in_pdf_path_remain_one_literal_argument(self):
        self.write_workflow()
        self.assertEqual(self.run_workflow_update().returncode, 0)
        with self.workflow.open("rb") as stream:
            command = plistlib.load(stream)["actions"][0]["action"]["ActionParameters"]["COMMAND_STRING"]
        home = self.root / "isolated-home"
        helper_dir = home / "Library/Application Support/Studio/allow-and-open"
        helper_dir.mkdir(parents=True)
        helper = helper_dir / "allow-and-open.sh"
        helper.write_text(
            '#!/bin/bash\nprintf "%s\\0" "$PDF_MAGIC_REQUEST_ORIGIN" "$@" '
            '> "$HOME/captured.bin"\n',
            encoding="utf-8",
        )
        path = self.root / 'filename ; $(touch injected) & " # \n☁.pdf'
        original = b"%PDF-1.4\nnever execute a PDF\n"
        path.write_bytes(original)
        result = subprocess.run(
            ["/bin/bash", "-c", command, "finder", str(path)],
            env={"HOME": str(home), "PATH": "/usr/bin:/bin"},
            cwd=home, capture_output=True, timeout=5,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual((home / "captured.bin").read_bytes(),
                         b"finder\x00" + os.fsencode(str(path)) + b"\x00")
        self.assertFalse((home / "injected").exists())
        self.assertEqual(path.read_bytes(), original)

    def test_missing_or_duplicate_finder_action_cannot_modify_workflow(self):
        for count in (0, 2):
            with self.subTest(actions=count):
                self.write_workflow(action_count=count)
                before = self.workflow.read_bytes()
                rejected = self.run_workflow_update()
                self.assertNotEqual(rejected.returncode, 0)
                self.assertEqual(self.workflow.read_bytes(), before)
                self.assertFalse(
                    self.workflow.with_name("document.wflow.before-brave").exists()
                )


    def test_user_authored_shell_command_is_never_overwritten(self):
        original = self.write_workflow()
        original["actions"][0]["action"]["ActionParameters"]["COMMAND_STRING"] = (
            "echo user customization; exit 0"
        )
        self.workflow.write_bytes(plistlib.dumps(original))
        before = self.workflow.read_bytes()
        result = self.run_workflow_update()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.workflow.read_bytes(), before)
        self.assertFalse(self.workflow.with_name("document.wflow.before-brave").exists())

    def test_repeated_migration_preserves_workflow_and_original_backup(self):
        original = self.write_workflow()
        self.assertEqual(self.run_workflow_update().returncode, 0)
        backup = self.workflow.with_name("document.wflow.before-brave")
        self.assertEqual(plistlib.loads(backup.read_bytes()), original)
        first_bytes = self.workflow.read_bytes()
        first_stat = self.workflow.stat()
        self.assertEqual(self.run_workflow_update().returncode, 0)
        self.assertEqual(self.workflow.read_bytes(), first_bytes)
        self.assertEqual(self.workflow.stat().st_ino, first_stat.st_ino)
        self.assertEqual(plistlib.loads(backup.read_bytes()), original)

    def test_workflow_and_backup_symlinks_are_rejected(self):
        self.write_workflow()
        original = self.workflow.read_bytes()
        target = self.root / "user-workflow.plist"
        target.write_bytes(original)
        self.workflow.unlink()
        self.workflow.symlink_to(target)
        self.assertNotEqual(self.run_workflow_update().returncode, 0)
        self.assertEqual(target.read_bytes(), original)
        self.workflow.unlink()
        self.workflow.write_bytes(original)

        backup = self.workflow.with_name("document.wflow.before-brave")
        backup.symlink_to(self.root / "absent-user-backup")
        self.assertNotEqual(self.run_workflow_update().returncode, 0)
        self.assertEqual(self.workflow.read_bytes(), original)
        self.assertTrue(backup.is_symlink())

    def test_malformed_workflow_is_left_unchanged(self):
        self.workflow.write_bytes(b"not a property list")
        before = self.workflow.read_bytes()
        self.assertNotEqual(self.run_workflow_update().returncode, 0)
        self.assertEqual(self.workflow.read_bytes(), before)
        self.assertFalse(self.workflow.with_name("document.wflow.before-brave").exists())

    def test_binary_workflow_preserves_other_actions_and_format(self):
        original = self.write_workflow()
        self.workflow.write_bytes(plistlib.dumps(original, fmt=plistlib.FMT_BINARY))
        self.assertEqual(self.run_workflow_update().returncode, 0)
        self.assertTrue(self.workflow.read_bytes().startswith(b"bplist00"))
        result = plistlib.loads(self.workflow.read_bytes())
        self.assertEqual(result["actions"][1], original["actions"][1])
        self.assertEqual(result["otherPreferences"], original["otherPreferences"])


if __name__ == "__main__":
    unittest.main()
