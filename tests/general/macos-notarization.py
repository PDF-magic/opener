#!/usr/bin/env python3
"""Offline notarization regressions: no Apple account or live submission."""

import json
from pathlib import Path
import plistlib
import stat
import sys
import subprocess
import tempfile
import unittest
from unittest.mock import patch
import zipfile

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))
import notarize_release as notary  # noqa: E402

TEAM_ID = "A1B2C3D4E5"
SUBMISSION_ID = "12345678-1234-1234-1234-123456789abc"


def zip_app(path, *, malicious=None):
  with zipfile.ZipFile(path, "w") as archive:
    archive.writestr(malicious or notary.APP_NAME + "/Contents/Info.plist", b"plist")


class NotarizationTests(unittest.TestCase):
  def setUp(self):
    temporary = tempfile.TemporaryDirectory()
    self.addCleanup(temporary.cleanup)
    self.root = Path(temporary.name)
    self.signed = self.root / "PDFMagicOpener-signed.zip"
    self.output = self.root / "PDFMagicOpener-notarized.zip"
    zip_app(self.signed)
    self.commands = []
    self.info_status = "Accepted"
    self.submit_status = "Accepted"
    self.fail_on = None

  def command(self, args, *, timeout=120):
    self.commands.append(args)
    if self.fail_on is not None and self.fail_on in args:
      raise notary.NotarizationError("Required release verification or Apple tool failed")
    if args[:3] == ["ditto", "-x", "-k"]:
      (Path(args[-1]) / notary.APP_NAME).mkdir()
    elif args[:3] == ["ditto", "-c", "-k"]:
      zip_app(Path(args[-1]))
    elif args[:3] == ["xcrun", "notarytool", "submit"]:
      return subprocess.CompletedProcess(args, 0, json.dumps({"id": SUBMISSION_ID, "status": self.submit_status}), "")
    elif args[:3] == ["xcrun", "notarytool", "info"]:
      return subprocess.CompletedProcess(args, 0, json.dumps({"id": SUBMISSION_ID, "status": self.info_status}), "")
    return subprocess.CompletedProcess(args, 0, "", "")

  def perform(self):
    with patch.object(notary, "checked", side_effect=self.command), \
         patch.object(notary, "verify_signed_app") as verified:
      result = notary.notarize(self.signed, self.output, apple_id="developer@example.invalid",
                               password="private-placeholder", team_id=TEAM_ID)
    self.assertEqual(verified.call_count, 2)
    return result

  def test_only_accepted_and_rechecked_ticket_can_publish(self):
    self.assertEqual(self.perform(), SUBMISSION_ID)
    self.assertTrue(self.output.is_file())
    operations = [args[:3] for args in self.commands]
    self.assertLess(operations.index(["xcrun", "notarytool", "submit"]),
                    operations.index(["xcrun", "notarytool", "info"]))
    self.assertLess(operations.index(["xcrun", "notarytool", "info"]),
                    operations.index(["xcrun", "stapler", "staple"]))
    self.assertIn(["xcrun", "stapler", "validate"], operations)
    self.assertTrue(any(args[:3] == ["spctl", "--assess", "--type"] for args in self.commands))

  def test_missing_credentials_and_existing_outputs_are_refused(self):
    for apple_id, password, team in (("", "p", TEAM_ID), ("a", "", TEAM_ID),
                                      ("a", "p", "bad")):
      with self.subTest(team=team, apple_id=apple_id), self.assertRaises(notary.NotarizationError):
        notary.notarize(self.signed, self.output, apple_id=apple_id,
                        password=password, team_id=team)
    self.assertEqual(self.commands, [])
    self.output.write_bytes(b"existing")
    with self.assertRaises(notary.NotarizationError):
      self.perform()
    self.assertEqual(self.output.read_bytes(), b"existing")

  def test_rejected_submission_or_failed_independent_info_cannot_publish(self):
    for attribute in ("submit_status", "info_status"):
      setattr(self, attribute, "Invalid")
      with self.subTest(attribute=attribute), self.assertRaises(notary.NotarizationError):
        self.perform()
      self.assertFalse(self.output.exists())
      setattr(self, attribute, "Accepted")

  def test_failed_stapling_or_gatekeeper_cannot_publish(self):
    for failure in ("staple", "validate", "spctl"):
      self.fail_on = failure
      with self.subTest(failure=failure), self.assertRaises(notary.NotarizationError):
        self.perform()
      self.assertFalse(self.output.exists())
    self.fail_on = None

  def test_archive_paths_and_escape_symlinks_fail_before_submission(self):
    for name in ("../outside", "/tmp/invalid", notary.APP_NAME + "/../evil"):
      zip_app(self.signed, malicious=name)
      with self.subTest(name=name), self.assertRaises(notary.NotarizationError):
        self.perform()
    with zipfile.ZipFile(self.signed, "w") as archive:
      entry = zipfile.ZipInfo(notary.APP_NAME + "/Contents/Frameworks/outside")
      entry.create_system = 3
      entry.external_attr = (stat.S_IFLNK | 0o777) << 16
      archive.writestr(entry, "../../../../../../etc/passwd")
    with self.assertRaises(notary.NotarizationError):
      self.perform()
    self.assertFalse(self.output.exists())
    self.assertEqual(self.commands, [])

  def test_ditto_metadata_entries_are_safe(self):
    with zipfile.ZipFile(self.signed, "a") as archive:
      archive.writestr("__MACOSX/", b"")
      archive.writestr("__MACOSX/._" + notary.APP_NAME, b"metadata")
    notary.validate_zip(self.signed)

  def test_malformed_notary_response_blocks_release(self):
    with patch.object(notary, "checked", return_value=subprocess.CompletedProcess([], 0, "[]", "")):
      with self.assertRaises(notary.NotarizationError):
        notary.notary_json(["info", SUBMISSION_ID], ["--team-id", TEAM_ID])

  def test_signature_requires_correct_identity_team_runtime_and_developer_id(self):
    app = self.root / notary.APP_NAME
    (app / "Contents/Helpers").mkdir(parents=True)
    with (app / "Contents/Info.plist").open("wb") as stream:
      plistlib.dump({"CFBundleIdentifier": notary.BUNDLE_ID}, stream)
    good = "\n".join(("Identifier=" + notary.BUNDLE_ID,
                       "TeamIdentifier=" + TEAM_ID,
                       "Authority=Developer ID Application: Example (" + TEAM_ID + ")",
                       "CodeDirectory v=20500 size=400 flags=0x10000(runtime)"))
    with patch.object(notary, "validate_helpers"), \
         patch.object(notary, "checked", return_value=subprocess.CompletedProcess([], 0, good, good)):
      notary.verify_signed_app(app, TEAM_ID)
    for missing in ("Authority=Developer ID Application", "TeamIdentifier=" + TEAM_ID,
                    "(runtime)", "Identifier=" + notary.BUNDLE_ID):
      with self.subTest(missing=missing), patch.object(notary, "validate_helpers"), \
           patch.object(notary, "checked", return_value=subprocess.CompletedProcess([], 0, good.replace(missing, "REMOVED"), "")), \
           self.assertRaises(notary.NotarizationError):
        notary.verify_signed_app(app, TEAM_ID)

  def test_ci_is_offline_and_real_notarization_requires_explicit_dispatch(self):
    workflow = (ROOT / ".github/workflows/notarize-macos.yml").read_text()
    tests = (ROOT / ".github/workflows/notarization-tests.yml").read_text()
    self.assertIn("workflow_dispatch:", workflow)
    self.assertNotIn("pull_request:", workflow)
    self.assertIn("github.ref == 'refs/heads/main'", workflow)
    self.assertIn(".head_sha", workflow)
    self.assertIn(".conclusion", workflow)
    self.assertIn("environment: macos-notarization", workflow)
    self.assertIn("name: signed-macos-app", workflow)
    self.assertIn("name: notarized-macos-app", workflow)
    self.assertIn("secrets.NOTARY_APP_PASSWORD", workflow)
    self.assertIn("python3 scripts/notarize_release.py", workflow)
    self.assertIn("pull_request:", tests)
    self.assertIn("merge_group:", tests)
    self.assertIn("tests/general/macos-notarization.py", tests)


if __name__ == "__main__":
  unittest.main()
