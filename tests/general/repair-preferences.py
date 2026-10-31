#!/usr/bin/env python3
"""Exercise confirmed repair against real installer preference initializers.

No real PDF Magic installation, Homebrew process, LaunchAgent service, or
user preferences are accessed; all mutable paths are in a synthetic HOME.
"""

import os
from pathlib import Path
import plistlib
import pty
import re
import select
import signal
import subprocess
import sys
import tempfile
import time
import unittest

ROOT = Path(__file__).resolve().parents[2]
INSTALLER = ROOT / "install-allow-and-open.sh"
REPAIR = ROOT / "Repair Installation.command"
MIGRATOR = ROOT / "scripts/migrate_update_agent.py"
sys.dont_write_bytecode = True


def initializer(source, marker):
    match = re.search(marker + r"\n(.*?)\n(?:TARGET_APP|CONFIG)\n",
                      source, re.DOTALL)
    if match is None:
        raise AssertionError("Required preference initializer was removed")
    return match.group(1)


class RepairPreferencesTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.installer = INSTALLER.read_text(encoding="utf-8")
        cls.target = initializer(
            cls.installer, r"python3 - \"\$install_dir/target-app\.txt\" <<'TARGET_APP'")
        cls.freshclam = initializer(
            cls.installer, r"python3 - \"\$install_dir\" <<'CONFIG'")
        cls.agent = initializer(
            cls.installer, r"python3 - \"\$app\" \"\$install_dir\" \"\$app_name\" <<'CONFIG'")

    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="repair-preferences-")
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.home = self.root / "home"
        self.install = self.home / "Library/Application Support/Studio/allow-and-open"
        self.install.mkdir(parents=True)
        self.agents = self.home / "Library/LaunchAgents"
        self.agents.mkdir(parents=True)
        (self.home / "Library/Logs/Studio").mkdir(parents=True)
        self.app = self.home / "Applications/PDF Magic Opener.app"
        (self.app / "Contents").mkdir(parents=True)
        self.checkout = self.root / "trusted-checkout"
        self.checkout.mkdir()
        self.repair = self.checkout / REPAIR.name
        self.repair.write_bytes(REPAIR.read_bytes())
        self.repair.chmod(0o755)
        scripts = self.checkout / "scripts"
        scripts.mkdir()
        for name in ("report_install_prerequisites.py", "confirm_clamav_install.py"):
            (scripts / name).write_text("# test fixture\n", encoding="utf-8")
        self.marker = self.root / "repair-ran"
        self.fixture = self.checkout / "simulate-managed-initializers.py"
        self.fake_installer = self.checkout / INSTALLER.name
        # This is an inert fixture, never the real installer. The three snippets
        # come verbatim from the real installer and run only under synthetic HOME.
        python_source = (
            "import os, subprocess, sys\n"
            "from pathlib import Path\n"
            "home = Path(os.environ['HOME'])\n"
            "install = home / 'Library/Application Support/Studio/allow-and-open'\n"
            "app = home / 'Applications/PDF Magic Opener.app'\n"
            f"target_code = {self.target!r}\n"
            f"config_code = {self.freshclam!r}\n"
            f"agent_code = {self.agent!r}\n"
            "for code, args in ((target_code, [str(install / 'target-app.txt')]),\n"
            "                   (config_code, [str(install)]),\n"
            "                   (agent_code, [str(app), str(install), 'PDF Magic Opener'])):\n"
            "    subprocess.run([sys.executable, '-c', code, *args],\n"
            "                   check=True, timeout=8)\n"
            f"subprocess.run([sys.executable, {str(MIGRATOR)!r}], check=True, timeout=8)\n"
            f"Path({str(self.marker)!r}).write_text('ran', encoding='ascii')\n"
        )
        self.fixture.write_text(python_source, encoding="utf-8")
        self.fake_installer.write_text(
            '#!/bin/bash\nset -euo pipefail\n'
            'python3 "$(dirname "$0")/simulate-managed-initializers.py"\n',
            encoding="utf-8",
        )

    def snapshot(self, files):
        return {
            str(path): (path.read_bytes(), path.stat().st_ino,
                        path.stat().st_mtime_ns, path.stat().st_mode & 0o777)
            for path in files
        }

    def populate_preferences(self):
        # Sentinels model existing user settings; no test reads a real home.
        choice = self.install / "target-app.txt"
        choice.write_bytes(b"org.mozilla.firefox\n")
        fallback = self.install / "fallback-app.txt"
        fallback.write_bytes(b"com.apple.Preview\n")
        config = self.install / "freshclam.conf"
        config.write_bytes(
            b"DatabaseMirror private-mirror.invalid\n"
            b"HTTPProxyServer proxy.invalid\n"
            b"ScriptedUpdates no\n# Custom settings must survive repair\n"
        )
        agent = self.agents / "local.studio.pdf-malware-signatures.plist"
        settings = {
            "Label": "local.studio.pdf-malware-signatures",
            "ProgramArguments": ["/bin/bash", str(self.install / "update-malware-signatures.sh")],
            "StartInterval": 5400,
            "RunAtLoad": False,
            "Disabled": True,
            "ProcessType": "Background",
            "StandardOutPath": str(self.home / "Library/Logs/Studio/pdf-malware-signatures.log"),
            "StandardErrorPath": str(self.home / "Library/Logs/Studio/pdf-malware-signatures.error.log"),
        }
        agent.write_bytes(plistlib.dumps(settings))
        preferences = self.home / "Library/Preferences/com.studio.pdf-magic-opener.plist"
        preferences.parent.mkdir(parents=True)
        preferences.write_bytes(plistlib.dumps({
            "selectedBrowser": "org.mozilla.firefox",
            "scanNotificationOptIn": False, "customLimits": 37,
        }))
        quick_action = self.home / "Library/Services/Allow and Open.workflow/Contents/document.wflow"
        quick_action.parent.mkdir(parents=True)
        quick_action.write_bytes(b"custom Finder script and unrelated workflow actions")
        extra = self.install / "custom-user-file"
        extra.write_bytes(b"Retain all user additions")
        return [choice, fallback, config, agent, preferences, quick_action, extra]

    def run_repair(self, *, authorize):
        # forkpty provides a real controlling terminal, unlike piped REPAIR
        # text. The authorized process executes only our synthetic fixture.
        if not authorize:
            result = subprocess.run(
                ["/bin/bash", str(self.repair)], input="REPAIR\n",
                capture_output=True, text=True, timeout=8,
                start_new_session=True, env=dict(os.environ, HOME=str(self.home)),
            )
            self.assertNotEqual(result.returncode, 0)
            return result.returncode

        if os.geteuid() == 0:
            self.skipTest("Interactive repair explicitly refuses root")
        child, master = pty.fork()
        if child == 0:
            os.environ["HOME"] = str(self.home)
            os.execv("/bin/bash", ["/bin/bash", str(self.repair)])
        end = time.monotonic() + 15
        buffer = b""
        responded = False
        done = False
        try:
            while time.monotonic() < end:
                ready, _, _ = select.select([master], [], [], 0.2)
                if ready:
                    try:
                        chunk = os.read(master, 65536)
                    except OSError:  # EIO after PTY slave closes
                        chunk = b""
                    buffer += chunk
                    if b"Type REPAIR" in buffer and not responded:
                        os.write(master, b"REPAIR\n")
                        responded = True
                pid, status = os.waitpid(child, os.WNOHANG)
                if pid:
                    done = True
                    code = os.waitstatus_to_exitcode(status)
                    self.assertTrue(responded, "Repair did not present its authorization prompt")
                    self.assertEqual(code, 0, buffer[-1200:].decode("utf-8", errors="replace"))
                    return
            self.fail("Synthetic repair did not complete within the bounded timeout")
        finally:
            if not done:
                os.kill(child, signal.SIGKILL)
                os.waitpid(child, 0)
            os.close(master)

    def test_declined_or_unattended_repair_keeps_all_preferences(self):
        saved = self.populate_preferences()
        before = self.snapshot(saved)
        self.run_repair(authorize=False)
        self.assertFalse(self.marker.exists())
        self.assertEqual(before, self.snapshot(saved))

    def test_two_confirmed_repairs_preserve_every_existing_preference(self):
        saved = self.populate_preferences()
        before = self.snapshot(saved)
        for _ in range(2):
            self.run_repair(authorize=True)
            self.assertTrue(self.marker.exists())
            self.assertEqual(before, self.snapshot(saved))

    def test_fresh_repair_creates_defaults_without_resetting_user_preferences(self):
        settings = self.home / "Library/Preferences/other-app.plist"
        settings.parent.mkdir(parents=True)
        settings.write_bytes(b"other application must not change")
        prior = self.snapshot([settings])
        self.run_repair(authorize=True)
        self.assertEqual((self.install / "target-app.txt").read_bytes(), b"com.brave.Browser\n")
        self.assertIn(b"DatabaseMirror", (self.install / "freshclam.conf").read_bytes())
        agent = plistlib.loads(
            (self.agents / "local.studio.pdf-malware-signatures.plist").read_bytes()
        )
        self.assertEqual(agent["StartInterval"], 14400)
        self.assertEqual(prior, self.snapshot([settings]))

    def test_repair_delegates_to_installer_without_reset_commands(self):
        source = REPAIR.read_text(encoding="utf-8")
        self.assertIn('exec /bin/bash "$installer"', source)
        self.assertIn('if [ "$response" != "REPAIR" ]; then', source)
        self.assertLess(source.index('if [ "$response" != "REPAIR" ]; then'),
                        source.index('exec /bin/bash "$installer"'))
        for forbidden in ("defaults write", "defaults delete", "plutil -replace",
                          "target-app.txt", "fallback-app.txt", "freshclam.conf",
                          "LaunchAgents/", "rm -rf", "\\nsudo ", "\\n    sudo "):
            with self.subTest(forbidden=forbidden):
                self.assertNotIn(forbidden, source)
        # Existing choices are only initialized when absent; the companion
        # FreshClam config and LaunchAgent behave the same on repair.
        self.assertIn("os.O_EXCL", self.target)
        self.assertIn("os.O_EXCL", self.freshclam)
        self.assertIn("os.O_EXCL", self.agent)
        self.assertIn('scripts/migrate_update_agent.py', self.installer)

    def test_new_ci_suite_covers_explicit_repair_preference_preservation(self):
        ci = (ROOT / ".github/workflows/ci.yml").read_text()
        self.assertIn("tests/general/repair-preferences.py -v", ci)
        self.assertIn("tests/general/repair-installation.py -v", ci)
        self.assertIn("tests/general/persistent-installer-preferences.py -v", ci)


if __name__ == "__main__":
    unittest.main()
