#!/usr/bin/env python3
"""Hermetic Repair Installation action tests (opener-0965)."""

import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
REPAIR = ROOT / "Repair Installation.command"
INSTALLER = ROOT / "install-allow-and-open.sh"


class RepairInstallationTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="opener-repair-")
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.repair = self.root / REPAIR.name
        shutil.copyfile(REPAIR, self.repair)
        self.repair.chmod(0o755)
        scripts = self.root / "scripts"
        scripts.mkdir()
        for name in ("report_install_prerequisites.py", "confirm_clamav_install.py"):
            (scripts / name).write_text("# test fixture only\n", encoding="utf-8")
        self.marker = self.root / "installer-ran"
        self.installer = self.root / INSTALLER.name
        self.installer.write_text(
            '#!/bin/bash\nprintf "called" > "' + str(self.marker) + '"\n',
            encoding="utf-8",
        )

    def invoke_without_tty(self, *arguments, path=None):
        return subprocess.run(
            ["/bin/bash", str(path or self.repair), *arguments],
            input="REPAIR\n", text=True, capture_output=True,
            start_new_session=True, timeout=8,
        )

    def test_requires_controlling_terminal_not_piped_input(self):
        completed = self.invoke_without_tty()
        self.assertNotEqual(completed.returncode, 0)
        self.assertFalse(self.marker.exists())
        self.assertIn("terminal", completed.stderr.lower())

    def test_rejects_options_before_running_installer(self):
        completed = self.invoke_without_tty("--yes")
        self.assertNotEqual(completed.returncode, 0)
        self.assertFalse(self.marker.exists())

    def test_missing_or_symlinked_installer_is_rejected(self):
        self.installer.unlink()
        self.assertNotEqual(self.invoke_without_tty().returncode, 0)
        self.assertFalse(self.marker.exists())
        target = self.root / "other-installer"
        target.write_text("#!/bin/bash\n", encoding="utf-8")
        self.installer.symlink_to(target)
        self.assertNotEqual(self.invoke_without_tty().returncode, 0)
        self.assertFalse(self.marker.exists())

    def test_repair_action_symlink_is_rejected(self):
        alias = self.root / "alias.command"
        alias.symlink_to(self.repair)
        completed = self.invoke_without_tty(path=alias)
        self.assertNotEqual(completed.returncode, 0)
        self.assertFalse(self.marker.exists())

    def test_shell_syntax_and_authorization_boundary(self):
        compiled = subprocess.run(
            ["/bin/bash", "-n", str(REPAIR)], capture_output=True, text=True,
            timeout=8,
        )
        self.assertEqual(compiled.returncode, 0, compiled.stderr)
        source = REPAIR.read_text(encoding="utf-8")
        self.assertIn('if [ "$EUID" -eq 0 ]; then', source)
        self.assertIn('IFS= read -r response < /dev/tty', source)
        self.assertIn('if [ "$response" != "REPAIR" ]; then', source)
        self.assertIn('exec /bin/bash "$installer"', source)
        self.assertLess(source.index('if [ "$response" != "REPAIR" ]; then'),
                        source.index('exec /bin/bash "$installer"'))
        for unexpected in ("brew install", "curl ", "wget ", "eval ",
                           "rm -rf", "target-app.txt", "clamscan --"):
            with self.subTest(unexpected=unexpected):
                self.assertNotIn(unexpected, source)
        # Explain that sudo is prohibited without mistaking the notice for
        # a command invocation.
        self.assertNotIn("\\nsudo ", source)
        self.assertNotIn("\\n    sudo ", source)

    def test_established_installer_skips_healthy_scanner_and_preserves_preferences(self):
        source = INSTALLER.read_text(encoding="utf-8")
        preflight = source.index("if ! [ -x /opt/homebrew/bin/clamscan ]")
        installation = source.index('"$brew_executable" install clamav')
        end = source.index("\nfi", preflight)
        self.assertLess(preflight, installation)
        self.assertLess(installation, end)
        self.assertIn("scripts/confirm_clamav_install.py", source[preflight:end])
        self.assertIn("except FileExistsError:", source)
        self.assertIn("ScriptedUpdates yes", source)
        self.assertIn("migration_attempt=", source)
        self.assertIn("migration_committed=1", source)
        self.assertLess(
            source.index('complete "$migration_attempt"'),
            source.index("migration_committed=1"),
        )

    def test_documentation_and_ci_expose_real_repair_action(self):
        readme = (ROOT / "README.md").read_text(encoding="utf-8")
        doc = (ROOT / "docs/repair-installation.md").read_text(encoding="utf-8")
        ci = (ROOT / ".github/workflows/ci.yml").read_text(encoding="utf-8")
        self.assertIn("Repair Installation.command", readme)
        self.assertIn("Repair Installation.command", doc)
        self.assertIn("REPAIR", doc)
        self.assertIn("tests/general/repair-installation.py -v", ci)
        self.assertTrue(REPAIR.is_file())


if __name__ == "__main__":
    unittest.main()
