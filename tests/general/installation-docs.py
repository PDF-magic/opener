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

  def test_discoverable_installation_path_matches_real_installer(self):
    guide_path = ROOT / "docs/installation-path.md"
    self.assertTrue(guide_path.is_file())
    guide = guide_path.read_text(encoding="utf-8")
    index = (ROOT / "docs/README.md").read_text(encoding="utf-8")
    installer = (ROOT / "install-allow-and-open.sh").read_text(encoding="utf-8")
    self.assertIn("[source installation instructions](docs/installation-path.md)", self.installation)
    self.assertIn("[Install PDF Magic Opener from source](installation-path.md)", index)
    self.assertIn("bash install-allow-and-open.sh", guide)
    self.assertIn("Do not treat CI-built unsigned ZIPs as", guide)
    self.assertIn("not a self-contained clean-Mac installer", guide)
    self.assertIn("Do not disable Gatekeeper", guide)
    self.assertIn("Open With → PDF Magic Opener", guide)
    self.assertIn("scripts/migration_state.py status", guide)
    self.assertIn("~/Applications/PDF Magic Opener.app", guide)
    self.assertIn("browser inline/embedded PDF viewers", guide)
    self.assertIn('if [ "$EUID" -eq 0 ]; then', installer)
    self.assertIn('if [ ! -f "$workflow" ]; then', installer)
    self.assertIn('python3 "$script_dir/scripts/report_install_prerequisites.py"', installer)
    self.assertIn('install_dir="$HOME/Library/Application Support/Studio/allow-and-open"', installer)

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
