#!/usr/bin/env python3
"""Upgrade the original Brave-only installation in a disposable user home.

This integration fixture runs the real installer's Python migration blocks
and staged-bundle swap. It deliberately avoids installing software, running
the updater, registering a handler, or executing a PDF.
"""

import os
from pathlib import Path
import plistlib
import re
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
INSTALLER = (ROOT / "install-allow-and-open.sh").read_text(encoding="utf-8")
BUNDLE_ID = "local.studio.brave-pdf-opener"
APP_NAME = "PDF Magic Opener.app"
AGENT_NAME = "local.studio.pdf-malware-signatures.plist"
LEGACY_COMMAND = (
  '/bin/bash "$HOME/Library/Application Support/Studio/'
  'allow-and-open/allow-and-open.sh" "$@"\n'
)
NEW_COMMAND = (
  'export PDF_MAGIC_REQUEST_ORIGIN=finder\n'
  'exec /bin/bash "$HOME/Library/Application Support/Studio/'
  'allow-and-open/allow-and-open.sh" "$@"\n'
)


def heredoc(marker, end):
  if INSTALLER.count(marker) != 1:
    raise AssertionError("Missing or ambiguous installer migration: " + marker)
  return INSTALLER.split(marker, 1)[1].split("\n" + end + "\n", 1)[0]


TARGET = heredoc('python3 - "$install_dir/target-app.txt" <<\'TARGET_APP\'\n', "TARGET_APP")
FRESHCLAM = heredoc('python3 - "$install_dir" <<\'CONFIG\'\n', "CONFIG")
RENAME = heredoc('python3 - "$legacy_app" "$app" <<\'MIGRATE\'\n', "MIGRATE")
APP_CONFIG = heredoc('python3 - "$app" "$install_dir" "$app_name" <<\'CONFIG\'\n', "CONFIG")
FINDER = heredoc('python3 - "$workflow" <<\'PY\'\n', "PY")
SWAP_START = 'if [ -e "$installed_app" ] || [ -L "$installed_app" ]; then\n'
SWAP_END = '\napp="$installed_app"\n'
if INSTALLER.count(SWAP_START) != 1:
  raise AssertionError("Missing or ambiguous staged application swap")
SWAP = SWAP_START + INSTALLER.split(SWAP_START, 1)[1].split(SWAP_END, 1)[0] + SWAP_END


class BraveOnlyUpgradeTests(unittest.TestCase):
  def setUp(self):
    temporary = tempfile.TemporaryDirectory(prefix="opener-brave-upgrade-")
    self.addCleanup(temporary.cleanup)
    self.home = Path(temporary.name) / "home"
    self.apps = self.home / "Applications"
    self.legacy = self.apps / "Open PDFs in Brave.app"
    self.installed = self.apps / APP_NAME
    self.install = self.home / "Library/Application Support/Studio/allow-and-open"
    self.agents = self.home / "Library/LaunchAgents"
    self.logs = self.home / "Library/Logs/Studio"
    self.workflow = self.home / "Library/Services/Allow and Open.workflow/Contents/document.wflow"
    for path in (self.apps, self.install, self.agents, self.logs, self.workflow.parent):
      path.mkdir(parents=True)

  def run_python(self, source, *args, expected=0):
    completed = subprocess.run(
      [sys.executable, "-c", source, *map(str, args)],
      env=dict(os.environ, HOME=str(self.home)),
      capture_output=True, text=True, timeout=10,
    )
    self.assertEqual(completed.returncode, expected, completed.stderr)
    return completed

  def fixture(self, browser="com.brave.Browser", identifier=BUNDLE_ID):
    contents = self.legacy / "Contents"
    (contents / "MacOS").mkdir(parents=True)
    (contents / "MacOS/PDFOpener").write_bytes(b"original Brave-only handler")
    (contents / "Info.plist").write_bytes(plistlib.dumps({"CFBundleIdentifier": identifier}))
    (self.install / "allow-and-open.sh").write_text("#!/bin/sh\nexit 9\n")
    (self.install / "scan-and-open.py").write_text("# original scanner stub\n")
    (self.install / "target-app.txt").write_text(browser + "\n")
    (self.install / "freshclam.conf").write_bytes(
      b"DatabaseMirror mirror.example.org\n# preserved proxy customization\n")
    signatures = self.install / "signatures"
    signatures.mkdir()
    (signatures / "main.cvd").write_bytes(b"legacy main signatures")
    (signatures / "daily.cld").write_bytes(b"legacy daily signatures")
    (signatures / "last-successful-update").write_text("1234567890\n")
    (self.install / "previous-pdf-handler.txt").write_text("com.apple.Preview\n")

    agent = {
      "Label": "local.studio.pdf-malware-signatures",
      "ProgramArguments": ["/bin/bash", str(self.install / "update-malware-signatures.sh")],
      "StartInterval": 21600,
      "RunAtLoad": False,
      "ProcessType": "Background",
      "StandardOutPath": str(self.logs / "custom-update.log"),
      "StandardErrorPath": str(self.logs / "custom-errors.log"),
    }
    (self.agents / AGENT_NAME).write_bytes(plistlib.dumps(agent))
    workflow = {
      "actions": [
        {"action": {
          "BundleIdentifier": "com.apple.RunShellScript",
          "ActionParameters": {
            "COMMAND_STRING": LEGACY_COMMAND,
            "inputMethod": 0,
            "shell": "/bin/zsh",
            "userSetting": "untouched",
          },
        }},
        {"action": {
          "BundleIdentifier": "com.example.custom-action",
          "ActionParameters": {"custom": "retain"},
        }},
      ],
      "userPreferences": {"favorite": "Brave-only"},
    }
    self.workflow.write_bytes(plistlib.dumps(workflow))
    return agent, workflow

  def snapshot(self):
    paths = [
      self.install / "allow-and-open.sh",
      self.install / "scan-and-open.py",
      self.install / "target-app.txt",
      self.install / "freshclam.conf",
      self.install / "signatures/main.cvd",
      self.install / "signatures/daily.cld",
      self.install / "signatures/last-successful-update",
      self.install / "previous-pdf-handler.txt",
    ]
    return {str(path.relative_to(self.home)): (path.read_bytes(), path.stat().st_ino)
            for path in paths}

  def upgrade(self):
    # Execute the actual installer's initializers and legacy bundle migration.
    probe = subprocess.run(
      [sys.executable, str(ROOT / "scripts/detect_existing_scan_scripts.py"), str(self.install)],
      capture_output=True, text=True, timeout=10,
    )
    self.assertEqual(probe.returncode, 0, probe.stderr)
    self.assertIn("Existing scan scripts detected:", probe.stdout)
    self.run_python(TARGET, self.install / "target-app.txt")
    self.run_python(FRESHCLAM, self.install)
    self.run_python(RENAME, self.legacy, self.installed)

    # The real compiled binaries and signing are covered by the macOS CI job.
    # Here staged contents meet the production pre-install verifier contract.
    stage = Path(tempfile.mkdtemp(prefix=".pdf-magic-opener-build.", dir=self.apps))
    staged_app = stage / APP_NAME
    (staged_app / "Contents/MacOS").mkdir(parents=True)
    (staged_app / "Contents/Resources").mkdir()
    for filename in ("PDFOpener", "MakePDFMagicDefault"):
      binary = staged_app / "Contents/MacOS" / filename
      binary.write_bytes(b"test executable fixture")
      binary.chmod(0o755)
    (staged_app / "Contents/Resources/twilight-reading.png").write_bytes(
      b"\x89PNG\r\n\x1a\nfixture")
    self.run_python(APP_CONFIG, staged_app, self.install, "PDF Magic Opener")
    verified = subprocess.run(
      [sys.executable, str(ROOT / "scripts/verify_pdf_opener_bundle.py"), str(staged_app)],
      capture_output=True, text=True, timeout=10,
    )
    self.assertEqual(verified.returncode, 0, verified.stderr)

    result = subprocess.run(
      ["/bin/bash", "-eu", "-c", SWAP],
      env=dict(os.environ, installed_app=str(self.installed),
               bundle_stage_dir=str(stage), app=str(staged_app)),
      capture_output=True, text=True, timeout=10,
    )
    self.assertEqual(result.returncode, 0, result.stderr)
    agent_result = subprocess.run(
      [sys.executable, str(ROOT / "scripts/migrate_update_agent.py")],
      env=dict(os.environ, HOME=str(self.home)),
      capture_output=True, text=True, timeout=10,
    )
    self.assertEqual(agent_result.returncode, 0, agent_result.stderr)
    self.run_python(FINDER, self.workflow)
    return stage / "previous.app"

  def test_brave_only_upgrade_preserves_existing_configuration_and_backup(self):
    original_agent, original_workflow = self.fixture()
    snapshot = self.snapshot()
    previous = self.upgrade()
    self.assertFalse(self.legacy.exists())
    self.assertEqual((previous / "Contents/MacOS/PDFOpener").read_bytes(),
                     b"original Brave-only handler")
    self.assertEqual(plistlib.loads((self.installed / "Contents/Info.plist").read_bytes())
                     ["CFBundleIdentifier"], BUNDLE_ID)
    for relative, (content, inode) in snapshot.items():
      path = self.home / relative
      self.assertEqual(path.read_bytes(), content, relative)
      self.assertEqual(path.stat().st_ino, inode, relative)
    self.assertEqual(plistlib.loads((self.agents / AGENT_NAME).read_bytes()), original_agent)
    updated_workflow = plistlib.loads(self.workflow.read_bytes())
    params = updated_workflow["actions"][0]["action"]["ActionParameters"]
    self.assertEqual(params["COMMAND_STRING"], NEW_COMMAND)
    self.assertEqual(params["userSetting"], "untouched")
    self.assertEqual(updated_workflow["actions"][1], original_workflow["actions"][1])
    self.assertEqual(updated_workflow["userPreferences"], original_workflow["userPreferences"])
    self.assertEqual(plistlib.loads(self.workflow.with_name("document.wflow.before-brave").read_bytes()),
                     original_workflow)

  def test_custom_browser_selection_survives_brave_only_upgrade(self):
    self.fixture(browser="org.mozilla.firefox")
    snapshot = self.snapshot()
    self.upgrade()
    self.assertEqual((self.install / "target-app.txt").read_text(), "org.mozilla.firefox\n")
    self.assertEqual(self.snapshot(), snapshot)

  def test_unverified_brave_bundle_fails_without_modifying_user_files(self):
    self.fixture(identifier="com.example.unrelated")
    snapshot = self.snapshot()
    self.run_python(RENAME, self.legacy, self.installed, expected=1)
    self.assertTrue(self.legacy.is_dir())
    self.assertFalse(self.installed.exists())
    self.assertEqual(self.snapshot(), snapshot)
    self.assertFalse(self.workflow.with_name("document.wflow.before-brave").exists())

  def test_conflicting_new_bundle_fails_without_replacing_either(self):
    self.fixture()
    (self.installed / "Contents").mkdir(parents=True)
    (self.installed / "Contents/Info.plist").write_bytes(
      plistlib.dumps({"CFBundleIdentifier": BUNDLE_ID}))
    original_bytes = (self.installed / "Contents/Info.plist").read_bytes()
    snapshot = self.snapshot()
    self.run_python(RENAME, self.legacy, self.installed, expected=1)
    self.assertEqual((self.installed / "Contents/Info.plist").read_bytes(), original_bytes)
    self.assertTrue(self.legacy.is_dir())
    self.assertEqual(self.snapshot(), snapshot)

  def test_upgrade_rerun_does_not_destroy_previous_finder_backup(self):
    self.fixture()
    snapshot = self.snapshot()
    self.upgrade()
    backup = self.workflow.with_name("document.wflow.before-brave")
    before = backup.read_bytes()
    self.upgrade()
    self.assertFalse(self.legacy.exists())
    self.assertEqual(backup.read_bytes(), before)
    self.assertEqual(self.snapshot(), snapshot)

  def test_installer_stages_and_verifies_before_installing_or_registering(self):
    verify = 'python3 "$script_dir/scripts/verify_pdf_opener_bundle.py" "$app"'
    self.assertIn(verify, INSTALLER)
    self.assertLess(INSTALLER.index(verify), INSTALLER.index(SWAP_START))
    self.assertLess(INSTALLER.index(SWAP_START), INSTALLER.index("lsregister -f"))
    self.assertLess(INSTALLER.index('python3 "$script_dir/scripts/migrate_update_agent.py"'),
                    INSTALLER.index('launchctl bootout "gui/$UID"'))
    self.assertIn('bash "$install_dir/update-malware-signatures.sh"', INSTALLER)
    scanner = (ROOT / "scan-and-open.py").read_text()
    self.assertIn("check_database()", scanner)
    self.assertIn("MAX_DATABASE_AGE = 48 * 60 * 60", scanner)
    self.assertIn("python3 tests/migration/brave-only-upgrade.py -v",
                  (ROOT / ".github/workflows/ci.yml").read_text())


if __name__ == "__main__":
  unittest.main()
