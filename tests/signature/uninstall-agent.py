#!/usr/bin/env python3
"""Synthetic opt-in LaunchAgent removal tests; no real launchctl or user home."""

from pathlib import Path
import importlib.util
import os
import plistlib
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location(
    "uninstall_signature_launchagent", ROOT / "uninstall_signature_launchagent.py")
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)


class FakeLaunchctl:
    def __init__(self, loaded=False, fail_bootout=False, unknown=False, still_loaded=False):
        self.loaded = loaded
        self.fail_bootout = fail_bootout
        self.unknown = unknown
        self.still_loaded = still_loaded
        self.calls = []

    def __call__(self, argv):
        self.calls.append(argv)
        if argv[1] == "print":
            if self.unknown:
                return subprocess.CompletedProcess(argv, 1, "", "permission denied")
            if self.loaded:
                return subprocess.CompletedProcess(argv, 0, "service present", "")
            return subprocess.CompletedProcess(argv, 113, "", "Could not find service")
        if argv[1] == "bootout":
            if self.fail_bootout:
                return subprocess.CompletedProcess(argv, 1, "", "failed")
            if not self.still_loaded:
                self.loaded = False
            return subprocess.CompletedProcess(argv, 0, "", "")
        raise AssertionError(f"Unexpected command: {argv}")


class SignatureLaunchAgentUninstallTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory(prefix="uninstall-agent-0989-")
        self.addCleanup(tmp.cleanup)
        self.home = Path(tmp.name)
        self.folder = self.home / "Library/LaunchAgents"
        self.folder.mkdir(parents=True)
        self.plist = self.folder / mod.AGENT_FILENAME
        self.backup = self.folder / mod.BACKUP_FILENAME
        self.info = {
            "Label": mod.AGENT_LABEL,
            "ProgramArguments": [
                "/bin/bash", str(self.home / "Library/Application Support/Studio/"
                                 "allow-and-open/update-malware-signatures.sh")],
            "StartInterval": 237,
            "Disabled": True,
            "StandardOutPath": str(self.home / "Library/Logs/Studio/keep-user-custom.log"),
        }
        self.plist.write_bytes(plistlib.dumps(self.info))
        self.original = self.plist.read_bytes()
        self.other = self.folder / "org.example.other.plist"
        self.other.write_bytes(b"unrelated")
        self.owner = patch.object(mod.os, "geteuid", return_value=501)
        self.owner.start()
        self.addCleanup(self.owner.stop)

    def test_inspection_only_and_loaded_service_never_removed_implicitly(self):
        runner = FakeLaunchctl(loaded=True)
        inode = self.plist.stat().st_ino
        self.assertIn("rerun with --remove",
                      mod.remove_signature_launchagent(self.home, run=runner))
        self.assertEqual(self.plist.stat().st_ino, inode)
        self.assertEqual(self.plist.read_bytes(), self.original)
        self.assertFalse(self.backup.exists())
        self.assertEqual([c[1] for c in runner.calls], ["print"])

    def test_retire_exact_service_preserve_custom_plist_and_other_agents(self):
        runner = FakeLaunchctl(loaded=True)
        result = mod.remove_signature_launchagent(self.home, remove=True, run=runner)
        self.assertIn("removed", result)
        self.assertFalse(self.plist.exists())
        self.assertEqual(self.backup.read_bytes(), self.original)
        self.assertEqual(plistlib.loads(self.backup.read_bytes()), self.info)
        self.assertEqual(self.other.read_bytes(), b"unrelated")
        self.assertEqual([c[1] for c in runner.calls],
                         ["print", "bootout", "print", "print"])
        self.assertEqual(runner.calls[1], [
            "/bin/launchctl", "bootout", f"gui/{os.getuid()}", str(self.plist)])
        self.assertIn("absent", mod.remove_signature_launchagent(
            self.home, remove=True, run=FakeLaunchctl()))
        self.assertEqual(self.backup.read_bytes(), self.original)

    def test_unloaded_agent_can_be_archived_without_bootout(self):
        runner = FakeLaunchctl()
        mod.remove_signature_launchagent(self.home, remove=True, run=runner)
        self.assertEqual([c[1] for c in runner.calls], ["print", "print", "print"])
        self.assertEqual(self.backup.read_bytes(), self.original)

    def test_absent_and_loaded_without_plist_refuse(self):
        self.plist.unlink()
        self.assertIn("absent", mod.remove_signature_launchagent(self.home,
                      remove=True, run=FakeLaunchctl()))
        with self.assertRaises(mod.AgentRemovalRefused):
            mod.remove_signature_launchagent(self.home, remove=True,
                                             run=FakeLaunchctl(loaded=True))

    def test_unknown_or_failed_launchctl_never_deletes(self):
        for runner in (FakeLaunchctl(unknown=True), FakeLaunchctl(loaded=True, fail_bootout=True),
                       FakeLaunchctl(loaded=True, still_loaded=True)):
            with self.subTest(runner=vars(runner)):
                with self.assertRaises(mod.AgentRemovalRefused):
                    mod.remove_signature_launchagent(self.home, remove=True, run=runner)
                self.assertEqual(self.plist.read_bytes(), self.original)
                self.assertFalse(self.backup.exists())

    def test_changed_symlinked_unrecognized_and_hardlinked_plists_are_refused(self):
        for change in ("wrong-label", "wrong-command", "symlink", "hardlink", "bad-plist"):
            with self.subTest(change=change):
                self.plist.unlink(missing_ok=True)
                self.plist.write_bytes(self.original)
                target = self.folder / "extra-link"
                target.unlink(missing_ok=True)
                if change == "wrong-label":
                    modified = dict(self.info, Label="com.example.other")
                    self.plist.write_bytes(plistlib.dumps(modified))
                if change == "wrong-command":
                    modified = dict(self.info, ProgramArguments=["/bin/bash", "/tmp/untrusted"])
                    self.plist.write_bytes(plistlib.dumps(modified))
                if change == "symlink":
                    self.plist.unlink()
                    self.plist.symlink_to(self.other)
                if change == "hardlink":
                    os.link(self.plist, target)
                if change == "bad-plist":
                    self.plist.write_bytes(b"not a plist")
                with self.assertRaises(mod.AgentRemovalRefused):
                    mod.remove_signature_launchagent(self.home, remove=True, run=FakeLaunchctl())
                self.assertEqual(self.other.read_bytes(), b"unrelated")
                self.assertFalse(self.backup.exists())

    def test_prior_archive_never_overwritten(self):
        self.backup.write_bytes(b"keep the first uninstall archive")
        with self.assertRaises(mod.AgentRemovalRefused):
            mod.remove_signature_launchagent(self.home, remove=True, run=FakeLaunchctl())
        self.assertEqual(self.plist.read_bytes(), self.original)
        self.assertEqual(self.backup.read_bytes(), b"keep the first uninstall archive")

    def test_directory_symlink_is_refused(self):
        original_directory = self.home / "Library"
        moved = self.home / "original-library"
        original_directory.rename(moved)
        original_directory.symlink_to(moved)
        with self.assertRaises(mod.AgentRemovalRefused):
            mod.remove_signature_launchagent(self.home, remove=True, run=FakeLaunchctl())
        self.assertEqual((moved / "LaunchAgents" / mod.AGENT_FILENAME).read_bytes(),
                         self.original)

    def test_no_root_and_no_implicit_os_mutations(self):
        with patch.object(mod.os, "geteuid", return_value=0):
            with self.assertRaises(mod.AgentRemovalRefused):
                mod.remove_signature_launchagent(self.home, remove=True, run=FakeLaunchctl())
        code = (ROOT / "uninstall_signature_launchagent.py").read_text()
        self.assertNotIn("shell=True", code)
        self.assertNotIn("rm -", code)
        self.assertNotIn("brew uninstall", code)
        self.assertIn('parser.add_argument("--remove"', code)
        self.assertIn('answer != "REMOVE"', code)

    def test_uninstall_guide_and_ci_integrate_explicit_safe_removal(self):
        guide = (ROOT / "docs/uninstall-procedure.md").read_text()
        workflow = (ROOT / ".github/workflows/ci.yml").read_text()
        self.assertIn("python3 uninstall_signature_launchagent.py --remove", guide)
        self.assertIn("local.studio.pdf-malware-signatures.plist.before-uninstall", guide)
        self.assertIn("PYTHONPATH=. python3 tests/signature/uninstall-agent.py -v", workflow)
        self.assertIn("Verify guided uninstall procedure and safety boundaries", workflow)


if __name__ == "__main__":
    unittest.main()
