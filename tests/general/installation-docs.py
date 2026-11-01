#!/usr/bin/env python3
"""Verify scanner installation docs do not make Brave a prerequisite."""

from pathlib import Path
import re
import unittest


ROOT = Path(__file__).resolve().parents[2]
README = ROOT / "README.md"


class InstallationDocsTests(unittest.TestCase):
  @classmethod
  def setUpClass(cls):
    cls.readme = README.read_text(encoding="utf-8")
    cls.installation = cls.readme.split("## Installation and usage\n", 1)[1].split(
      "\n## ", 1
    )[0]

  def test_retains_scanner_install_command(self):
    self.assertIn("bash install-allow-and-open.sh", self.installation)
    self.assertIn("**Allow and Open**", self.installation)

  def test_brave_is_optional_for_installation(self):
    self.assertIn("**not an installation prerequisite**", self.installation)
    self.assertIn("does not install Brave or require Brave", self.installation)
    self.assertNotRegex(
      self.readme,
      re.compile(
        r"\bBrave(?: Browser)?\s+(?:is\s+)?(?:needed|required|mandatory)\b",
        re.IGNORECASE,
      ),
    )

  def test_documents_safe_alternative_target(self):
    self.assertIn("**General → Default PDF browser**", self.installation)
    self.assertIn("`target-app.txt`", self.installation)
    self.assertIn("An unavailable destination blocks opening", self.installation)
    self.assertIn("selected application must be installed and pass PDF-capability verification", self.readme)


if __name__ == "__main__":
  unittest.main()
