#!/usr/bin/env python3
"""Ensure the user-facing README describes the actual protection-level contract."""

from pathlib import Path
import unittest

from protection_profiles import PROTECTION_PROFILES, ProtectionProfileID


ROOT = Path(__file__).resolve().parents[2]
README = ROOT / "README.md"


class ProtectionLevelDocumentationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        readme = README.read_text(encoding="utf-8")
        cls.section = readme.split("## Protection levels\n", 1)[1].split("\n## ", 1)[0]

    def test_exactly_three_catalogued_levels_are_explained(self):
        self.assertEqual(
            {definition.display_name for definition in PROTECTION_PROFILES.values()},
            {"Standard", "Enhanced", "Maximum"},
        )
        for identifier in ProtectionProfileID:
            label = PROTECTION_PROFILES[identifier].display_name
            with self.subTest(level=label):
                self.assertEqual(
                    sum(line.startswith(f"| **{label}** |") for line in self.section.splitlines()),
                    1,
                )
        self.assertEqual(self.section.count("Preview only —"), 3)

    def test_actual_scan_gate_is_distinguished_from_preview_levels(self):
        for phrase in (
            "Currently enforced: Built-in",
            "ClamAV malware scanning",
            "current signature checks",
            "file-integrity",
            "fail-closed verified handoff",
            "preview-only",
            "never activates",
            "not active scanning engines",
        ):
            with self.subTest(phrase=phrase):
                self.assertIn(phrase, self.section)
        for definition in PROTECTION_PROFILES.values():
            self.assertFalse(definition.selectable)

    def test_required_and_optional_stages_remain_truthfully_planned(self):
        for phrase in (
            "Standard** | Retains the four Built-in safeguards",
            "PDF structure validation is an optional planned check",
            "Enhanced** | Retains all four safeguards and requires planned PDF structure validation",
            "isolated behavior analysis is optional and planned",
            "Maximum** | Inherits all Enhanced requirements",
            "additionally requires planned isolated behavior analysis",
            "mandatory PDF structure validation and isolated behavior analysis are not integrated",
            "No representative end-to-end performance comparison",
        ):
            with self.subTest(phrase=phrase):
                self.assertIn(phrase, self.section)

    def test_reference_links_resolve_to_existing_documents(self):
        for destination in (
            "docs/protection/settings-checks.md",
            "docs/protection/profile-dependencies.md",
            "docs/protection/settings-cards.md",
        ):
            self.assertIn("(" + destination + ")", self.section)
            self.assertTrue((ROOT / destination).is_file(), destination)


if __name__ == "__main__":
    unittest.main()
