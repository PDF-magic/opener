#!/usr/bin/env python3
"""Keep quarantined-file guidance aligned with the active native scan gate."""

from pathlib import Path
import re
import unittest

ROOT = Path(__file__).resolve().parents[2]
DOCUMENT = ROOT / "docs/quarantined-files.md"
INDEX = ROOT / "docs/README.md"
SCANNER = ROOT / "scan-and-open.py"
WORKFLOW = ROOT / ".github/workflows/ci.yml"


class QuarantinedFilesDocumentationTests(unittest.TestCase):
  @classmethod
  def setUpClass(cls):
    cls.guide = DOCUMENT.read_text(encoding="utf-8")
    cls.source = SCANNER.read_text(encoding="utf-8")

  def test_attribute_is_preserved_on_clean_cached_and_blocked_paths(self):
    for phrase in (
        "com.apple.quarantine", "byte-for-byte", "no-op",
        "complete clean", "90-day", "48 hours", "same",
        "Gatekeeper", "does **not** remove", "not** automatically covered",
    ):
      with self.subTest(phrase=phrase):
        self.assertIn(phrase.lower(), self.guide.lower())
    self.assertIn("def remove_quarantine(path):", self.source)
    hook = self.source.split("def remove_quarantine(path):", 1)[1].split(
        "\n@dataclass(frozen=True)", 1)[0]
    self.assertIn("return None", hook)
    self.assertNotIn("os.removexattr", hook)
    self.assertNotIn("subprocess.run", hook)
    self.assertRegex(self.source, r"(?m)^CACHE_TTL = 90 \* 24 \* 60 \* 60$")
    self.assertRegex(self.source, r"(?m)^MAX_DATABASE_AGE = 48 \* 60 \* 60$")

  def test_failed_or_unscannable_files_are_not_released(self):
    for phrase in (
        "Malware detected", "Incomplete or unscannable",
        "Scanner failure", "timeout", "cancellation", "changed bytes",
        "refuses", "no automatic bypass", "no-op", "original location",
        "does **not** provide", "no automatic", "do not reopen",
    ):
      with self.subTest(phrase=phrase):
        self.assertIn(phrase.lower(), self.guide.lower())
    for statement in (
        "if not decision.allowed:", "remember_clean(cache_id",
        "verify_file_integrity(path, before, identity)",
        "verify_launch_target(path, target_app=",
        "remove_quarantine(path)",
    ):
      with self.subTest(statement=statement):
        self.assertIn(statement, self.source)

  def test_safe_inspection_and_os_boundary_are_explained(self):
    for phrase in (
        "/usr/bin/xattr -p com.apple.quarantine",
        "absent attribute", "xattr -d", "xattr -c", "Gatekeeper",
        "different PDF handler", "saved protection", "other applications",
        "not** proof", "not** certify",
    ):
      with self.subTest(phrase=phrase):
        self.assertIn(phrase.lower(), self.guide.lower())

  def test_guide_links_exist_and_ci_exercises_contract(self):
    index = INDEX.read_text(encoding="utf-8")
    self.assertIn("[Handling quarantined files](quarantined-files.md)", index)
    workflow = WORKFLOW.read_text(encoding="utf-8")
    self.assertEqual(
        workflow.count("python3 tests/general/quarantined-files-documentation.py -v"),
        1,
    )
    links = re.findall(r"(?<!!)\[[^]]+\]\(([^)]+)\)", self.guide)
    self.assertGreaterEqual(len(links), 8)
    for target in links:
      if target.startswith(("https://", "http://", "#")):
        continue
      with self.subTest(target=target):
        self.assertTrue((DOCUMENT.parent / target).is_file(), target)


if __name__ == "__main__":
  unittest.main()
