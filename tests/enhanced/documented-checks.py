#!/usr/bin/env python3
"""opener-1113: document only checks represented by the Enhanced policy."""

from pathlib import Path
import re
import unittest

from protection_policy_definitions import PROTECTION_POLICIES, ProtectionProfileID


ROOT = Path(__file__).resolve().parents[2]
DOC = ROOT / "docs" / "enhanced" / "checks.md"
INDEX = ROOT / "docs" / "README.md"
CI = ROOT / ".github" / "workflows" / "consolidated-checks.yml"


class EnhancedDocumentationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.document = DOC.read_text(encoding="utf-8")

    def test_documented_checks_match_required_and_optional_policy(self):
        rows = re.findall(
            r"^\| `([a-z_]+)` \| (Required|Optional) \| `(current|planned)` \|",
            self.document,
            re.MULTILINE,
        )
        actual = {(control, category): availability
                  for control, category, availability in rows}
        policy = PROTECTION_POLICIES[ProtectionProfileID.ENHANCED]
        expected = {
            (entry.control.value, category): entry.availability.value
            for category, entries in (
                ("Required", policy.required_checks),
                ("Optional", policy.optional_checks),
            )
            for entry in entries
        }
        self.assertEqual(len(rows), len(actual), "Duplicate Enhanced check")
        self.assertEqual(actual, expected)
        self.assertFalse(policy.selectable)

    def test_explicitly_distinguishes_available_and_planned_behavior(self):
        for statement in (
            "Enhanced is planned and not selectable",
            "Built-in",
            "not wired into the installed gate",
            "not a guarantee that all these checks execute today",
            "not a clean ClamAV result",
            "does not",
            "quarantine",
            "preferences and custom viewer selections",
        ):
            with self.subTest(statement=statement):
                self.assertIn(statement, self.document)

    def test_discoverable_and_covered_in_policy_ci(self):
        self.assertIn(
            "[Enhanced checks](enhanced/checks.md)",
            INDEX.read_text(encoding="utf-8"),
        )
        self.assertIn(
            "PYTHONPATH=. python3 tests/enhanced/documented-checks.py -v",
            CI.read_text(encoding="utf-8"),
        )


if __name__ == "__main__":
    unittest.main()
