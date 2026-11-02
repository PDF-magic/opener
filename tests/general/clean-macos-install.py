#!/usr/bin/env python3
"""Credential-free tests for the disposable clean-mac installation gate."""

from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))
import verify_clean_mac_install as install  # noqa: E402


class CleanMacInstallTests(unittest.TestCase):
  def setUp(self):
    temporary = tempfile.TemporaryDirectory()
    self.addCleanup(temporary.cleanup)
    self.root = Path(temporary.name)
    self.archive = self.root / "PDFMagicOpener-notarized.zip"
    self.archive.write_bytes(b"fixture-only")
    self.target = self.root / "Applications" / install.APP_NAME
    self.target.parent.mkdir()
    self.team = "A1B2C3D4E5"

  def test_only_hosted_main_branch_mac_dispatch_is_accepted(self):
    environment = {
      "GITHUB_ACTIONS": "true",
      "GITHUB_EVENT_NAME": "workflow_dispatch",
      "GITHUB_REPOSITORY": "PDF-magic/opener",
      "GITHUB_REF": "refs/heads/main",
      "RUNNER_OS": "macOS",
      "RUNNER_ENVIRONMENT": "github-hosted",
      "RUNNER_TEMP": str(self.root),
    }
    self.assertEqual(install.require_disposable_runner(environment, "darwin"), self.root)
    for key in list(environment):
      with self.subTest(key=key):
        altered = dict(environment)
        altered[key] = "not-allowed"
        with self.assertRaises(install.CleanInstallError):
          install.require_disposable_runner(altered, "darwin")
    with self.assertRaises(install.CleanInstallError):
      install.require_disposable_runner(environment, "linux")

  def test_existing_application_or_symlink_is_never_replaced(self):
    self.target.mkdir()
    with self.assertRaises(install.CleanInstallError), patch.object(install, "validate_zip") as validate:
      install.verify_clean_install(self.archive, self.team, self.root, target=self.target)
    validate.assert_not_called()
    self.target.rmdir()
    self.target.symlink_to(self.root, target_is_directory=True)
    with self.assertRaises(install.CleanInstallError):
      install.verify_clean_install(self.archive, self.team, self.root, target=self.target)

  def test_invalid_inputs_fail_before_extraction_and_installation(self):
    with patch.object(install, "run_command") as commands:
      for team in ("", "bad", "ABCDEFGHIJK"):
        with self.subTest(team=team), self.assertRaises(install.CleanInstallError):
          install.verify_clean_install(self.archive, team, self.root, target=self.target)
      link = self.root / "linked.zip"
      link.symlink_to(self.archive)
      with self.assertRaises(install.CleanInstallError):
        install.verify_clean_install(link, self.team, self.root, target=self.target)
      with patch.object(install, "validate_zip", side_effect=install.NotarizationError("bad")):
        with self.assertRaises(install.CleanInstallError):
          install.verify_clean_install(self.archive, self.team, self.root, target=self.target)
      commands.assert_not_called()

  def test_install_validates_before_and_after_copy_and_launch(self):
    commands = []
    verified = []
    def fake_command(args, *, timeout=120):
      commands.append(args)
      if args[:3] == ["ditto", "-x", "-k"]:
        (Path(args[-1]) / install.APP_NAME).mkdir()
      elif args[:2] == ["sudo", "/usr/bin/ditto"]:
        self.target.mkdir()
    with patch.object(install, "validate_zip") as validate, \
         patch.object(install, "verify_signed_app", side_effect=lambda app, team: verified.append(app)), \
         patch.object(install, "run_command", side_effect=fake_command), \
         patch.object(install, "launch_installed_app") as launch:
      install.verify_clean_install(self.archive, self.team, self.root, target=self.target)
    validate.assert_called_once_with(self.archive)
    self.assertEqual(len(verified), 2)
    self.assertNotEqual(verified[0], verified[1])
    self.assertEqual(verified[1], self.target)
    self.assertEqual(sum(args[:3] == ["xcrun", "stapler", "validate"] for args in commands), 2)
    self.assertEqual(sum(args[:3] == ["spctl", "--assess", "--type"] for args in commands), 2)
    copied = next(i for i, args in enumerate(commands) if args[:2] == ["sudo", "/usr/bin/ditto"])
    quarantine = next(i for i, args in enumerate(commands) if args[:3] == ["sudo", "/usr/bin/xattr", "-w"])
    self.assertTrue(any(args[0] == "spctl" for args in commands[:copied]))
    self.assertLess(copied, quarantine)
    self.assertTrue(any(args[0] == "spctl" for args in commands[quarantine + 1:]))
    launch.assert_called_once()
    self.assertEqual(launch.call_args.args[0], self.target)

  def test_failed_trust_or_install_does_not_launch(self):
    for failure in ("trust", "copy"):
      with self.subTest(failure=failure), \
           patch.object(install, "validate_zip"), \
           patch.object(install, "verify_signed_app", side_effect=install.NotarizationError("bad") if failure == "trust" else None), \
           patch.object(install, "run_command", side_effect=install.CleanInstallError("copy failed") if failure == "copy" else None), \
           patch.object(install, "launch_installed_app") as launch, \
           self.assertRaises(install.CleanInstallError):
        install.verify_clean_install(self.archive, self.team, self.root, target=self.target)
        launch.assert_not_called()

  def test_workflow_requires_trusted_artifact_and_never_uses_pr_secrets(self):
    workflow = (ROOT / ".github/workflows/clean-macos-install.yml").read_text()
    for token in (
      "pull_request:", "merge_group:", "branches: [main]", "workflow_dispatch:",
      "persist-credentials: false", "runs-on: macos-latest",
      "github.event_name == 'workflow_dispatch'",
      "github.ref == 'refs/heads/main'",
      "test \"$current_main\" = \"$GITHUB_SHA\"",
      ".head_sha", ".conclusion", ".path",
      ".github/workflows/notarize-macos.yml",
      "name: notarized-macos-app",
      "PDFMagicOpener-notarized.zip",
      "scripts/verify_clean_mac_install.py",
      "tests/general/clean-macos-install.py",
    ):
      with self.subTest(token=token):
        self.assertIn(token, workflow)
    self.assertNotIn("secrets.", workflow)
    self.assertNotIn("CODE_SIGNING_ALLOWED=NO", workflow)
    self.assertNotIn("install-allow-and-open.sh", workflow)
    self.assertLess(workflow.index("Verify current main and successful trusted notarization"),
                    workflow.index("Download only the independently notarized application"))
    self.assertLess(workflow.index("Download only the independently notarized application"),
                    workflow.index("Verify genuine first-time installation and launch"))


if __name__ == "__main__":
  unittest.main()
