"""Guard the documented Standard preview against the live policy contract."""

from pathlib import Path
import re
import unittest

from protection_policy_definitions import (
  ControlAvailability,
  PROTECTION_POLICIES,
)
from protection_profiles import ProtectionProfileID

ROOT = Path(__file__).resolve().parents[2]
DOCUMENT = ROOT / "docs/protection/standard-checks.md"
README = ROOT / "README.md"
CHECK = re.compile(r"^- \*\*[^\n]+?\*\* \(`([a-z_]+)`\)", re.MULTILINE)


def section(contents, heading):
  start = "## " + heading + "\n"
  if contents.count(start) != 1:
    raise AssertionError(f"Missing or repeated documentation section: {heading}")
  return contents.split(start, 1)[1].split("\n## ", 1)[0]


class StandardDocumentationTests(unittest.TestCase):
  def test_required_checks_match_contract(self):
    contents = DOCUMENT.read_text(encoding="utf-8")
    policy = PROTECTION_POLICIES[ProtectionProfileID.STANDARD]
    documented = CHECK.findall(section(contents, "Required checks"))
    expected = [requirement.control.value for requirement in policy.requirements]
    self.assertEqual(documented, expected)
    self.assertTrue(all(requirement.availability is ControlAvailability.CURRENT
                        for requirement in policy.requirements))
    self.assertFalse(policy.selectable)

  def test_optional_check_is_planned_not_active(self):
    contents = DOCUMENT.read_text(encoding="utf-8")
    policy = PROTECTION_POLICIES[ProtectionProfileID.STANDARD]
    documented = CHECK.findall(section(contents, "Optional, planned check"))
    self.assertEqual(documented, [item.control.value for item in policy.optional_checks])
    self.assertTrue(all(item.availability is ControlAvailability.PLANNED
                        for item in policy.optional_checks))
    self.assertNotIn("isolated_behavior_analysis", documented)
    self.assertIn("isolated_behavior_analysis", section(contents, "Not included"))

  def test_reader_can_find_status_and_failure_boundaries(self):
    contents = DOCUMENT.read_text(encoding="utf-8")
    index = README.read_text(encoding="utf-8")
    for phrase in ("preview-only", "not a selectable", "Built-in", "48 hours",
                   "quarantine", "configured application", "not active",
                   'selectedProtectionProfile = "standard"'):
      with self.subTest(phrase=phrase):
        self.assertIn(phrase, contents)
    self.assertIn("[what Standard checks](docs/protection/standard-checks.md)", index)
    self.assertIn("PDF structure validation is optional and planned", index)


if __name__ == "__main__":
  unittest.main()
