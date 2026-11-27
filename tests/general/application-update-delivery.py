#!/usr/bin/env python3
"""Check opt-in and manual source-based macOS updates."""

from pathlib import Path
import plistlib
import re
import runpy
import subprocess
import tempfile
import unittest
from urllib.parse import urlsplit
from unittest.mock import Mock, patch

ROOT = Path(__file__).resolve().parents[2]
DOC = ROOT / "docs/application-update-delivery.md"


class ApplicationUpdateDeliveryTests(unittest.TestCase):
  @classmethod
  def setUpClass(cls):
    cls.guide = DOC.read_text(encoding="utf-8")
    cls.normalized = re.sub(r"\s+", " ", cls.guide.replace("**", "")).lower()

  def test_manual_trusted_source_and_explicit_installation(self):
    for required in (
      "complete trusted checkout", "PDF-magic/opener",
      "manual updates are the default", "no published binary update channel",
      "bash scripts/installation/install-allow-and-open.sh", "normal user", "macOS 13",
      "finish any active scans", "post-install verification",
      "upgrade procedure", "rollback",
    ):
      with self.subTest(required=required):
        self.assertIn(required.lower(), self.normalized)
    installer = (ROOT / "scripts/installation/install-allow-and-open.sh").read_text(encoding="utf-8")
    self.assertIn("scripts/report-install-prerequisites.py", installer)
    self.assertIn('if [ "$EUID" -eq 0 ]; then', installer)

  def test_no_binary_distribution_or_signing_is_planned(self):
    for required in (
      "No prebuilt release or signing plan",
      "does not establish GitHub Releases distribution",
      "no signing or notarization pipeline is planned",
      "source-based installation procedure is development-only",
      "NOT RELEASE READY", "Gatekeeper",
      "do not bypass Gatekeeper",
    ):
      with self.subTest(required=required):
        self.assertIn(required.lower(), self.normalized)
    for forbidden in (
      "intended public native macOS application delivery channel",
      "official GitHub Releases", "future public delivery decision",
      "browser-managed update requirements",
    ):
      with self.subTest(forbidden=forbidden):
        self.assertNotIn(forbidden.lower(), self.normalized)
    self.assertIn("no published binary update channel", self.normalized)

  def test_finder_setup_is_opt_in_and_configures_the_daily_agent(self):
    launcher = ROOT / "scripts/installation/automatic-updates.command"
    self.assertTrue(launcher.stat().st_mode & 0o111)
    module = runpy.run_path(str(launcher.with_name("repository-updates.py")))
    configure = module["configure"]
    label = module["LABEL"]
    self.assertIn("automatic-updates.command", self.normalized)
    with tempfile.TemporaryDirectory() as temporary:
      home = Path(temporary)
      directory = home / "repository-update"
      app = home / "PDF Magic Opener.app"
      agent = home / "Library/LaunchAgents" / f"{label}.plist"
      with patch("builtins.input", return_value=""):
        configure(home, directory, app)
      self.assertFalse(directory.exists())
      with patch("builtins.input", return_value="ENABLE"), \
           patch.dict(configure.__globals__, {"check_for_update": Mock()}) as namespace, \
           patch("subprocess.run") as launchctl:
        configure(home, directory, app)
        namespace["check_for_update"].assert_called_once_with(directory, app, interactive=True)
        self.assertEqual(launchctl.call_args.args[0][1], "bootstrap")
      config = plistlib.loads(agent.read_bytes())
      self.assertEqual(config["StartCalendarInterval"], {"Hour": 9, "Minute": 0})
      self.assertNotIn("RunAtLoad", config)
      self.assertNotIn("StartInterval", config)
      self.assertTrue((directory / "repository-updates.py").is_file())
      self.assertEqual(config["ProgramArguments"][-2:],
                       [str(directory / "repository-updates.py"), "--check"])
      with patch("builtins.input", return_value="DISABLE"), patch("subprocess.run") as launchctl:
        launchctl.return_value.returncode = 0
        configure(home, directory, app)
        self.assertEqual(launchctl.call_args.args[0][1], "bootout")
      self.assertFalse(agent.exists())

  def test_failed_install_is_retried_and_success_is_skipped(self):
    module = runpy.run_path(str(ROOT / "scripts/installation/repository-updates.py"))
    update = module["check_for_update"]
    commit = "a" * 40
    with tempfile.TemporaryDirectory() as temporary:
      directory = Path(temporary)
      app = directory / "PDF Magic Opener.app"
      executable = app / "Contents/MacOS/PDFOpener"
      executable.parent.mkdir(parents=True)
      executable.touch()
      metadata = app / "Contents/Info.plist"
      def git(command, *_args, **_kwargs):
        return {"ls-remote": f"{commit} refs/heads/main", "rev-parse": commit}.get(command, "")

      with patch.dict(update.__globals__, {"git": git}), patch("subprocess.run") as run:
        error = subprocess.CalledProcessError(1, "/bin/bash")
        run.side_effect = error
        with self.assertRaises(subprocess.CalledProcessError):
          update(directory, app)
        self.assertFalse(metadata.exists())
        def install(command, **kwargs):
          if command[0] == "/bin/bash":
            metadata.write_bytes(plistlib.dumps({
              "PDFMagicSourceCommit": kwargs["env"]["PDF_MAGIC_SOURCE_COMMIT"]
            }))
        run.side_effect = install
        run.reset_mock()
        update(directory, app)
        self.assertEqual(plistlib.loads(metadata.read_bytes())["PDFMagicSourceCommit"], commit)
        self.assertEqual(run.call_count, 2)
        self.assertIs(run.call_args_list[0].kwargs["stdin"], subprocess.DEVNULL)
        run.reset_mock()
        update(directory, app)
        run.assert_not_called()

  def test_app_update_preserves_security_and_separate_update_streams(self):
    for required in (
      "ClamAV", "48-hour", "FreshClam", "Browser extensions",
      "inactive", "manual unpacked reloads", "saved preferences",
      "Finder", "macOS default PDF", "quarantine", "rollback",
      "native messaging", "scan-before-open",
      "file-integrity", "signature", "Gatekeeper",
    ):
      with self.subTest(required=required):
        self.assertIn(required.lower(), self.normalized)
    view = (ROOT / "PDFMagicOpenerApp/UpdatesSettingsView.swift").read_text(encoding="utf-8")
    self.assertIn(
      "Checking for or installing application updates is not available from this page yet.",
      view,
    )
    self.assertIn("ManualUpdateActions.updateSignatures()", view)
    self.assertNotIn("downloadTask", view)

  def test_index_and_local_documentation_links(self):
    index = (ROOT / "docs/README.md").read_text(encoding="utf-8")
    self.assertIn("(application-update-delivery.md)", index)
    for link in re.findall(r"(?<!!)\[[^\]]+\]\(([^)]+)\)", self.guide):
      parsed = urlsplit(link)
      if not parsed.scheme and not parsed.netloc and parsed.path:
        with self.subTest(link=link):
          self.assertTrue((DOC.parent / parsed.path).is_file(), link)

  def test_required_ci_runs_policy_regressions(self):
    ci = (ROOT / ".github/workflows/ci.yml").read_text(encoding="utf-8")
    self.assertIn("python3 tests/general/application-update-delivery.py -v", ci)
    self.assertIn("python3 tests/general/upgrade-documentation.py -v", ci)


if __name__ == "__main__":
  unittest.main()
