"""Contract checks for the documented limitations of antivirus signatures."""

from pathlib import Path
import re
import unittest

ROOT = Path(__file__).resolve().parents[2]
DOCUMENT = ROOT / "docs/scanner/signature-limitations.md"
INDEX = ROOT / "docs/README.md"
SCANNER = ROOT / "scan-and-open.py"
WORKFLOW = ROOT / ".github/workflows/ci.yml"


class AntivirusSignatureDocumentationTests(unittest.TestCase):
  def setUp(self):
    self.document = DOCUMENT.read_text(encoding="utf-8")
    self.scanner = SCANNER.read_text(encoding="utf-8")

  def test_clean_scan_is_not_promised_to_be_safe(self):
    for term in ("a clean verdict", "not that a document is safe",
                 "newly emerging malware", "obfuscated", "polymorphic",
                 "embedded scripts", "links", "sandbox", "social-engineering"):
      with self.subTest(term=term):
        self.assertIn(term, self.document)
    self.assertIn("not active", self.document)

  def test_freshness_and_cache_numbers_match_actual_gate(self):
    self.assertRegex(self.scanner, r"(?m)^MAX_DATABASE_AGE = 48 \* 60 \* 60$")
    self.assertRegex(self.scanner, r"(?m)^CACHE_TTL = 90 \* 24 \* 60 \* 60$")
    self.assertIn("48 hours", self.document)
    self.assertIn("90-day", self.document)
    self.assertIn("not\nautomatically rescanned", self.document)
    self.assertIn("signature", self.document.lower())

  def test_failed_scans_and_quarantine_are_not_bypassed(self):
    for term in ("blocks opening", "block managed opening", "File Quarantine",
                 "verified-destination", "file-integrity", "not every PDF",
                 "no scan settings", "user-selected PDF application"):
      with self.subTest(term=term):
        self.assertIn(term.lower(), self.document.replace("**", "").lower())
    self.assertRegex(self.scanner, r"(?m)^def check_database\(\):")
    self.assertIn("check_database()", self.scanner)

  def test_doc_is_discoverable_and_ci_checks_it(self):
    self.assertIn("[Antivirus signature limitations](scanner/signature-limitations.md)",
                  INDEX.read_text(encoding="utf-8"))
    self.assertIn("python3 tests/general/antivirus-signature-documentation.py -v",
                  WORKFLOW.read_text(encoding="utf-8"))
    self.assertTrue((ROOT / "docs/macos-security-controls.md").is_file())
    self.assertTrue((ROOT / "docs/protection/standard-checks.md").is_file())


if __name__ == "__main__":
  unittest.main()
