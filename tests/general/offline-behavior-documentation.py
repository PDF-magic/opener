"""Offline behavior documentation contract against the installed scan gate."""

from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[2]
DOC = ROOT / "docs/offline-behavior.md"
INDEX = ROOT / "docs/README.md"
SCANNER = ROOT / "scan-and-open.py"
UPDATER = ROOT / "update-malware-signatures.sh"
WORKFLOW = ROOT / ".github/workflows/ci.yml"


class OfflineBehaviorDocumentationTests(unittest.TestCase):
  def setUp(self):
    self.doc = DOC.read_text(encoding="utf-8")
    self.scanner = SCANNER.read_text(encoding="utf-8")
    self.updater = UPDATER.read_text(encoding="utf-8")

  def test_offline_local_scan_is_conditional_not_a_bypass(self):
    for statement in ("installed native Built-in scan gate", "without\nInternet access",
                      "already present as a local", "does not fetch a PDF",
                      "not** permission to skip scanning", "quarantine",
                      "verified application handoff", "selected viewer"):
      with self.subTest(statement=statement):
        self.assertIn(statement, self.doc)
    self.assertIn("def scanner_path():", self.scanner)
    self.assertIn("def check_database():", self.scanner)
    self.assertIn("check_database()", self.scanner)

  def test_signature_freshness_is_mandatory_even_for_cache(self):
    self.assertIn("MAX_DATABASE_AGE = 48 * 60 * 60", self.scanner)
    self.assertIn("CACHE_TTL = 90 * 24 * 60 * 60", self.scanner)
    for statement in ("48 hours", "90-day SHA-256 clean-scan cache",
                      "even on a\n  previously cached clean file",
                      "Opening is **blocked**", "main", "daily",
                      "last-successful-update"):
      with self.subTest(statement=statement):
        self.assertIn(statement, self.doc)
    self.assertIn("check_database()", self.scanner)

  def test_network_update_does_not_become_offline_clean_verdict(self):
    self.assertIn("run_freshclam_with_network_recovery", self.updater)
    self.assertIn('for attempt in 1 2; do', self.updater)
    self.assertIn('run_freshclam_with_network_recovery "$updater"', self.updater)
    self.assertIn('stage_dir="$(/usr/bin/mktemp -d', self.updater)
    self.assertLess(
        self.updater.index('run_freshclam_with_network_recovery "$updater"'),
        self.updater.index('success_tmp='))
    for statement in ("FreshClam updater", "retained", "does not publish",
                      "does\n  not extend", "when connectivity is\nrestored"):
      with self.subTest(statement=statement):
        self.assertIn(statement, self.doc)

  def test_remote_browser_paths_are_not_claimed_to_be_scanned(self):
    for statement in ("already downloaded", "inline/embedded/remote PDFs",
                      "not automatically intercepted", "not active",
                      "Download a PDF locally first"):
      with self.subTest(statement=statement):
        self.assertIn(statement, self.doc)
    self.assertTrue((ROOT / "docs/browser-download-monitoring-support.md").is_file())

  def test_discoverability_and_required_ci_registration(self):
    self.assertIn("[Offline behavior](offline-behavior.md)",
                  INDEX.read_text(encoding="utf-8"))
    self.assertIn("python3 tests/general/offline-behavior-documentation.py -v",
                  WORKFLOW.read_text(encoding="utf-8"))
    for link in ("scanner/signature-limitations.md", "scanner/failure-response.md",
                 "browser-download-monitoring-support.md"):
      self.assertIn(f"({link})", self.doc)
      self.assertTrue((ROOT / "docs" / link).is_file())


if __name__ == "__main__":
  unittest.main()
