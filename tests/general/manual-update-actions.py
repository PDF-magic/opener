#!/usr/bin/env python3
"""opener-0381: signature update actions never alter scan safety."""
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[2]
VIEW = ROOT / "PDFMagicOpenerApp" / "UpdatesSettingsView.swift"
UPDATE = ROOT / "update-malware-signatures.sh"
SCAN = ROOT / "scan-and-open.py"
CI = ROOT / ".github/workflows/ci.yml"

class ManualActionTests(unittest.TestCase):
  def test_clicks_not_automatic_triggers(self):
    view = VIEW.read_text()
    self.assertEqual(view.count('Button("Check for Updates Now")'), 1)
    self.assertEqual(view.count('Button("Update Signatures Now")'), 1)
    self.assertIn(".disabled(checkingSignatureUpdates)", view)
    self.assertIn(".disabled(updatingSignatures)", view)
    self.assertNotIn(".onAppear", view)
    self.assertNotIn(".task(", view)

  def test_read_only_check_uses_bounded_clamav_revision_lookup(self):
    view = VIEW.read_text()
    for expected in ("current.cvd.clamav.net", '"/usr/bin/dig"',
                     'publishedRevisions(from: answer)',
                     'installedRevision("main", in: directory)',
                     'installedRevision("daily", in: directory)',
                     "O_NOFOLLOW", "data.count <= 512",
                     "Newer ClamAV signatures are advertised.",
                     "Could not verify published ClamAV signature revisions."):
      with self.subTest(expected=expected):
        self.assertIn(expected, view)
    self.assertNotIn("URLSession", view)
    self.assertNotIn("curl", view)

  def test_manual_signature_update_is_existing_bounded_command(self):
    view = VIEW.read_text()
    updater = UPDATE.read_text()
    self.assertIn('process.arguments = [script.path]', view)
    self.assertIn("lstat(script.path, &metadata)", view)
    self.assertIn("process.standardOutput = FileHandle.nullDevice", view)
    self.assertIn("process.standardError = FileHandle.nullDevice", view)
    self.assertIn("process.terminationStatus == 0", view)
    self.assertIn("last-attempted-update", updater)
    self.assertIn("last-successful-update", updater)
    self.assertIn("freshclam.conf", updater)
    self.assertIn("MAX_DATABASE_AGE = 48 * 60 * 60", SCAN.read_text())
    self.assertNotIn("scan_and_open(", view)

  def test_ci_executes_both_action_tests(self):
    ci = CI.read_text()
    self.assertIn("python3 tests/general/manual-update-actions.py -v", ci)
    self.assertIn("test-manual-update-actions.swift", ci)

if __name__ == "__main__":
  unittest.main()
