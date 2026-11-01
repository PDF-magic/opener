"""Keep the Maximum documentation aligned with the inactive policy contract."""

from pathlib import Path
import re
import unittest

from protection_policy_definitions import (
  ControlAvailability,
  FailureDisposition,
  PROTECTION_POLICIES,
)
from protection_profiles import ProtectionProfileID

ROOT = Path(__file__).resolve().parents[2]
DOCUMENT = ROOT / "docs/maximum/checks.md"
INDEX = ROOT / "docs/README.md"
CHECK = re.compile(r"^- \*\*[^\n]+?\*\* \(`([a-z_]+)`\)", re.MULTILINE)


def section(contents, heading):
  marker = "## " + heading + "\n"
  if contents.count(marker) != 1:
    raise AssertionError(f"Missing or repeated documentation section: {heading}")
  return contents.split(marker, 1)[1].split("\n## ", 1)[0]


class MaximumDocumentationTests(unittest.TestCase):
  def test_required_checks_match_contract_order_and_availability(self):
    contents = DOCUMENT.read_text(encoding="utf-8")
    policy = PROTECTION_POLICIES[ProtectionProfileID.MAXIMUM]
    required = section(contents, "Required checks")
    self.assertEqual(
      CHECK.findall(required),
      [requirement.control.value for requirement in policy.requirements],
    )
    self.assertEqual(
      [requirement.availability for requirement in policy.requirements],
      [ControlAvailability.CURRENT] * 4 + [ControlAvailability.PLANNED] * 2,
    )
    self.assertEqual(required.count("**Current"), 4)
    self.assertEqual(required.count("**Planned,"), 2)
    self.assertFalse(policy.selectable)
    self.assertIs(policy.failure_disposition, FailureDisposition.DENY)

  def test_maximum_inherits_enhanced_and_has_no_optional_checks(self):
    contents = DOCUMENT.read_text(encoding="utf-8")
    enhanced = PROTECTION_POLICIES[ProtectionProfileID.ENHANCED]
    maximum = PROTECTION_POLICIES[ProtectionProfileID.MAXIMUM]
    self.assertEqual(
      maximum.requirements[:len(enhanced.requirements)],
      enhanced.requirements,
    )
    self.assertEqual(
      maximum.requirements[len(enhanced.requirements):],
      enhanced.optional_checks,
    )
    self.assertEqual(maximum.optional_checks, ())
    optional = section(contents, "Optional checks")
    self.assertEqual(CHECK.findall(optional), [])
    self.assertIn("**None.**", optional)
    self.assertIn("promoting Enhanced's optional isolated analysis", optional)

  def test_never_claims_sanitization_grants_open_or_tier_is_live(self):
    contents = DOCUMENT.read_text(encoding="utf-8")
    for phrase in (
      "preview-only", "not a selectable", "Built-in", "48",
      "not enforced as a Maximum check", "resource-bounded",
      "separate fresh ClamAV scan", "file-integrity validation",
      "fail-closed handoff", "macOS quarantine", "non-selectable",
      "not proof", "user-selected destination",
    ):
      with self.subTest(phrase=phrase):
        self.assertIn(phrase, contents)
    for link in (
      "(enhanced-inheritance.md)",
      "(isolated-analysis.md)",
      "(isolated-renderer.md)",
      "(sanitized-copy.md)",
      "(safe-copy-handoff.md)",
    ):
      self.assertIn(link, contents)

  def test_doc_discoverable_from_technical_index(self):
    index = INDEX.read_text(encoding="utf-8")
    self.assertIn("[Maximum](maximum/checks.md)", index)


if __name__ == "__main__":
  unittest.main()
