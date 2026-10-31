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
        self.assertLess(installer.index(migration), installer.index('python3 "$script_dir/scripts/reconcile_update_agent.py"'))
        # Fresh-install provisioning is exclusive-create; the migrator owns upgrades.
        self.assertIn("os.O_EXCL | os.O_NOFOLLOW", installer)
        self.assertIn("except FileExistsError:", installer)
        self.assertNotIn("agent_path.write_bytes(", installer)
        self.assertIn("migrate_update_agent.py", installer)



class SingleActiveUpdateAgentTests(unittest.TestCase):
    """Behavioral launchctl tests without reading or modifying real agents."""

    def setUp(self):
        import importlib.util
        spec = importlib.util.spec_from_file_location(
            "reconcile_update_agent", ROOT / "scripts/reconcile_update_agent.py"
        )
        self.agent_module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.agent_module)

    def fake_launchctl(self, *, loaded=False, fail_bootout=False,
                       persist_after_bootout=False, fail_bootstrap=False,
                       fail_verification=False):
        state = {"loaded": loaded, "boots": 0, "calls": []}

        def run(args, **kwargs):
            state["calls"].append(args)
            self.assertEqual(args[0], "launchctl")
            self.assertIs(kwargs["check"], False)
            self.assertEqual(kwargs["stdout"], subprocess.DEVNULL)
            self.assertEqual(kwargs["stderr"], subprocess.DEVNULL)
            if args[1] == "print":
                code = 0 if state["loaded"] else 113
                if fail_verification and state["boots"]:
                    code = 113
            elif args[1] == "bootout":
                code = 5 if fail_bootout else 0
                if not code and not persist_after_bootout:
                    state["loaded"] = False
            elif args[1] == "bootstrap":
                state["boots"] += 1
                code = 5 if fail_bootstrap or state["loaded"] else 0
                if not code:
                    state["loaded"] = True
            else:
                self.fail("Unexpected launchctl command")
            return subprocess.CompletedProcess(args, code)

        return state, run

    def test_absent_agent_bootstraps_once(self):
        state, run = self.fake_launchctl()
        self.agent_module.reconcile(self.home_path(), 501, run)
        self.assertTrue(state["loaded"])
        self.assertEqual(state["boots"], 1)
        self.assertEqual([args[1] for args in state["calls"]],
                         ["print", "bootstrap", "print"])
        self.assertEqual(state["calls"][1][2], "gui/501")
        self.assertEqual(state["calls"][1][3], str(
            self.home_path() / "Library/LaunchAgents/local.studio.pdf-malware-signatures.plist"
        ))

    def home_path(self):
        return Path("/Users/synthetic-test-user")

    def test_preloaded_agent_is_stopped_by_service_label(self):
        state, run = self.fake_launchctl(loaded=True)
        self.agent_module.reconcile(self.home_path(), 501, run)
        self.assertTrue(state["loaded"])
        self.assertEqual(state["boots"], 1)
        self.assertEqual([args[1] for args in state["calls"]],
                         ["print", "bootout", "print", "bootstrap", "print"])
        self.assertEqual(
            state["calls"][1][2], "gui/501/local.studio.pdf-malware-signatures"
        )
        # Reinstalling again still leaves precisely one registered service.
        self.agent_module.reconcile(self.home_path(), 501, run)
        self.assertTrue(state["loaded"])
        self.assertEqual(state["boots"], 2)

    def test_failed_bootout_never_bootstraps_duplicate(self):
        state, run = self.fake_launchctl(loaded=True, fail_bootout=True)
        with self.assertRaises(self.agent_module.UpdateAgentReconciliationError):
            self.agent_module.reconcile(self.home_path(), 501, run)
        self.assertEqual(state["boots"], 0)

    def test_still_registered_old_agent_blocks_bootstrap(self):
        state, run = self.fake_launchctl(loaded=True, persist_after_bootout=True)
        with self.assertRaises(self.agent_module.UpdateAgentReconciliationError):
            self.agent_module.reconcile(self.home_path(), 501, run)
        self.assertEqual(state["boots"], 0)

    def test_registration_failures_refuse_success(self):
        for options in ({"fail_bootstrap": True}, {"fail_verification": True}):
            with self.subTest(options=options):
                state, run = self.fake_launchctl(**options)
                with self.assertRaises(self.agent_module.UpdateAgentReconciliationError):
                    self.agent_module.reconcile(self.home_path(), 501, run)
                self.assertEqual(state["boots"], 1)

    def test_installer_migrates_before_one_scoped_reconciliation(self):
        installer = (ROOT / "install-allow-and-open.sh").read_text()
        migrate = 'python3 "$script_dir/scripts/migrate_update_agent.py"'
        reconcile = 'python3 "$script_dir/scripts/reconcile_update_agent.py"'
        self.assertEqual(installer.count(reconcile), 1)
        self.assertLess(installer.index(migrate), installer.index(reconcile))
        self.assertLess(installer.index('verify_pdf_opener_bundle.py'),
                        installer.index(reconcile))
        self.assertNotIn('launchctl bootout "gui/$UID" "$agent"', installer)
        self.assertNotIn('launchctl bootstrap "gui/$UID" "$agent"', installer)

if __name__ == "__main__":
    unittest.main()
