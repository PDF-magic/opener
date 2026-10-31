#!/usr/bin/env python3
"""Synthetic, cross-platform LaunchAgent migration and installer wiring tests."""

import os
from pathlib import Path
import plistlib
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
MIGRATOR = ROOT / "scripts/migrate_update_agent.py"
AGENT = "local.studio.pdf-malware-signatures.plist"


class UpdateAgentMigrationTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="update-agent-migration-")
        self.addCleanup(temporary.cleanup)
        self.home = Path(temporary.name) / "home"
        self.agents = self.home / "Library/LaunchAgents"
        self.agents.mkdir(parents=True)
        (self.home / "Library/Logs/Studio").mkdir(parents=True)
        self.plist = self.agents / AGENT
        self.external = self.home / "outside-file"
        self.external.write_bytes(b"unrelated user data\n")
        self.updater = self.home / "Library/Application Support/Studio/allow-and-open/update-malware-signatures.sh"

    def run_migration(self, expected=0):
        result = subprocess.run(
            [sys.executable, str(MIGRATOR)],
            env=dict(os.environ, HOME=str(self.home)),
            capture_output=True, text=True,
        )
        self.assertEqual(result.returncode, expected, result.stderr)
        self.assertEqual(self.external.read_bytes(), b"unrelated user data\n")
        self.assertEqual(list(self.agents.glob(".*.tmp")), [])
        return result

    def write_plist(self, data):
        self.plist.write_bytes(plistlib.dumps(data))

    def test_fresh_install_creates_only_trusted_agent(self):
        self.run_migration()
        agent = plistlib.loads(self.plist.read_bytes())
        self.assertEqual(agent["ProgramArguments"], ["/bin/bash", str(self.updater)])
        self.assertEqual(agent["StartInterval"], 14400)
        self.assertTrue(agent["RunAtLoad"])
        self.assertEqual(self.plist.stat().st_mode & 0o777, 0o600)
        inode = self.plist.stat().st_ino
        self.run_migration()
        self.assertEqual(self.plist.stat().st_ino, inode)

    def test_existing_custom_schedule_logs_and_disabled_flag_survive(self):
        self.run_migration()
        agent = plistlib.loads(self.plist.read_bytes())
        agent.update(StartInterval=32760, RunAtLoad=False, Disabled=True)
        agent["StandardOutPath"] = str(self.home / "Library/Logs/Studio/custom-updates.log")
        self.write_plist(agent)
        before = self.plist.stat()
        self.run_migration()
        self.assertEqual(plistlib.loads(self.plist.read_bytes()), agent)
        self.assertEqual(self.plist.stat().st_ino, before.st_ino)

    def test_existing_calendar_schedule_survives(self):
        self.run_migration()
        agent = plistlib.loads(self.plist.read_bytes())
        del agent["StartInterval"]
        agent["StartCalendarInterval"] = [{"Hour": 3, "Minute": 20}, {"Hour": 15, "Minute": 20}]
        self.write_plist(agent)
        self.run_migration()
        self.assertEqual(plistlib.loads(self.plist.read_bytes()), agent)

    def test_invalid_agent_identity_and_unknown_keys_are_not_overwritten(self):
        self.run_migration()
        default = plistlib.loads(self.plist.read_bytes())
        for change in ({"Label": "someone.else"},
                       {"ProgramArguments": ["/bin/sh", "-c", "dangerous-command"]},
                       {"EnvironmentVariables": {"DANGEROUS": "1"}},
                       {"StartInterval": False}, {"RunAtLoad": "yes"},
                       {"StartCalendarInterval": {"Hour": 38}}):
            with self.subTest(change=change):
                candidate = dict(default, **change)
                self.write_plist(candidate)
                before = self.plist.read_bytes()
                self.run_migration(expected=1)
                self.assertEqual(self.plist.read_bytes(), before)

    def test_malformed_and_symlink_agents_are_not_replaced(self):
        self.plist.write_bytes(b"not a plist")
        self.run_migration(expected=1)
        self.assertEqual(self.plist.read_bytes(), b"not a plist")
        self.plist.unlink()
        self.plist.symlink_to(self.external)
        self.run_migration(expected=1)
        self.assertTrue(self.plist.is_symlink())
        self.plist.unlink()
        self.run_migration()
        self.assertEqual(plistlib.loads(self.plist.read_bytes())["StartInterval"], 14400)

    def test_unsafe_log_destinations_are_rejected(self):
        self.run_migration()
        agent = plistlib.loads(self.plist.read_bytes())
        agent["StandardErrorPath"] = str(self.external)
        self.write_plist(agent)
        original = self.plist.read_bytes()
        self.run_migration(expected=1)
        self.assertEqual(self.plist.read_bytes(), original)
        agent["StandardErrorPath"] = str(self.home / "Library/Logs/Studio/linked.log")
        (self.home / "Library/Logs/Studio/linked.log").symlink_to(self.external)
        self.write_plist(agent)
        self.run_migration(expected=1)
        self.assertEqual(self.external.read_bytes(), b"unrelated user data\n")

    def test_installer_migrates_after_verifying_bundle_before_bootout(self):
        installer = (ROOT / "install-allow-and-open.sh").read_text()
        migration = 'python3 "$script_dir/scripts/migrate_update_agent.py"'
        self.assertEqual(installer.count(migration), 1)
        self.assertLess(installer.index('python3 "$script_dir/scripts/verify_pdf_opener_bundle.py"'),
                        installer.index(migration))
        self.assertLess(installer.index(migration), installer.index('launchctl bootout "gui/$UID"'))
        self.assertNotIn("plistlib.dump(agent, stream)", installer)
        self.assertIn("migrate_update_agent.py", installer)


if __name__ == "__main__":
    unittest.main()
