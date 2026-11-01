"""Documentation contract for the installed ClamAV signature update process."""

from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[2]
DOC = ROOT / "docs/scanner/signature-update-process.md"
INDEX = ROOT / "docs/README.md"
README = ROOT / "README.md"
UPDATER = ROOT / "update-malware-signatures.sh"
STATUS = ROOT / "signature_update_status.py"
AGENT = ROOT / "signature_update_launchagent.py"
SETTINGS = ROOT / "PDFMagicOpenerApp/UpdatesSettingsView.swift"
SCANNER = ROOT / "scan-and-open.py"
CI = ROOT / ".github/workflows/ci.yml"


class SignatureUpdateDocumentationTests(unittest.TestCase):
  def setUp(self):
    self.doc = DOC.read_text(encoding="utf-8")
    self.updater = UPDATER.read_text(encoding="utf-8")

  def test_scheduled_and_manual_paths_match_existing_controls(self):
    settings = SETTINGS.read_text(encoding="utf-8")
    agent = AGENT.read_text(encoding="utf-8")
    for phrase in ("every four hours while logged in", "Check for Updates Now",
                   "Update Signatures Now", "bash update-malware-signatures.sh",
                   "freshclam.conf"):
      with self.subTest(phrase=phrase):
        self.assertIn(phrase, self.doc)
    self.assertIn("local.studio.pdf-malware-signatures", agent)
    self.assertIn('Button("Check for Updates Now")', settings)
    self.assertIn('Button("Update Signatures Now")', settings)
    self.assertIn('freshclam.conf', self.updater)
    self.assertIn("every four hours while logged in", README.read_text(encoding="utf-8"))

  def test_safe_staging_validation_and_publication(self):
    for phrase in ("exclusive update lock", "staging", "retry at most",
                   "incomplete downloads", "ClamAV scanner",
                   "last-attempted-update", "last-successful-update",
                   "rollback", "custom signatures"):
      with self.subTest(phrase=phrase):
        self.assertIn(phrase, self.doc)
    for marker in ('lock_dir=', 'stage_dir=', 'last-attempted-update',
                   'last-successful-update', 'run_freshclam_with_network_recovery',
                   'check_incomplete_downloads', '--database="$stage_dir"',
                   'backup_dir=', 'for database in main daily'):
      with self.subTest(marker=marker):
        self.assertIn(marker, self.updater)

  def test_status_failure_and_scan_gate_stay_distinct(self):
    status = STATUS.read_text(encoding="utf-8")
    scanner = SCANNER.read_text(encoding="utf-8")
    for marker in ("lastAttemptedUpdateUtc", "lastSuccessfulUpdateUtc"):
      self.assertIn(marker, self.doc)
      self.assertIn(marker, status)
    for marker in ("freshclam-error", "updater-unavailable",
                   "incomplete-download", "Signature update in progress",
                   "48-hour", "90-day", "block managed opening",
                   "does **not automatically rescan**"):
      self.assertIn(marker.lower(), self.doc.lower())
    self.assertIn("MAX_DATABASE_AGE = 48 * 60 * 60", scanner)
    self.assertIn("CACHE_TTL = 90 * 24 * 60 * 60", scanner)

  def test_document_is_linked_and_exercised_by_ci(self):
    self.assertIn("[Signature update process](scanner/signature-update-process.md)",
                  INDEX.read_text(encoding="utf-8"))
    self.assertIn("[signature update process](docs/scanner/signature-update-process.md)",
                  README.read_text(encoding="utf-8"))
    self.assertIn("python3 tests/general/signature-update-documentation.py -v",
                  CI.read_text(encoding="utf-8"))
    self.assertTrue((ROOT / "docs/scanner/signature-limitations.md").is_file())


if __name__ == "__main__":
  unittest.main()
