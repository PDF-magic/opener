#!/usr/bin/env python3
"""opener-0331: show exact, accurately labeled protection checks per level."""

from pathlib import Path
import re
import unittest

from protection_policy_definitions import (
    ControlAvailability,
    PROTECTION_POLICIES,
    ProtectionProfileID,
)

ROOT = Path(__file__).resolve().parent
VIEW = ROOT / "PDFMagicOpenerApp" / "ProtectionSettingsView.swift"
CI = ROOT / ".github" / "workflows" / "ci.yml"


class ProtectionLevelCheckDisplayTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.swift = VIEW.read_text(encoding="utf-8")
        cls.catalog = {}
        pattern = (
            r"static let (\w+) = ProtectionLevelCheck\(\s*"
            r'id: "([^"]+)",\s*'
            r'title: "([^"]+)",\s*'
            r'explanation: "([^"]+)",\s*'
            r"availability: \.(current|planned)\s*\)"
        )
        for key, check_id, title, detail, status in re.findall(pattern, cls.swift):
            cls.catalog[key] = (check_id, title, detail, status)

    def _level_keys(self, property_name, tier):
        body = self.swift.split(
            f"var {property_name}: [ProtectionLevelCheck] {{", 1
        )[1].split("\n  }\n", 1)[0]
        case = re.search(
            rf"case \.{tier}:\s*return (.*?)(?=\n    case \.|\n  \}})",
            body, re.DOTALL,
        )
        self.assertIsNotNone(case, (property_name, tier))
        value = case.group(1)
        values = []
        if "ProtectionLevelCheckCatalog.baseline" in value:
            values += ["clamav", "signatures", "integrity", "handoff"]
        values += re.findall(r"ProtectionLevelCheckCatalog\.(\w+)", value)
        return [key for key in values if key != "baseline"]

    def test_catalog_defines_the_exact_immutable_policy_control_ids(self):
        expected = {
            "clamav": "clamav_scan_gate",
            "signatures": "signature_freshness",
            "integrity": "file_integrity",
            "handoff": "fail_closed_handoff",
            "structure": "pdf_structure_validation",
            "isolated": "isolated_behavior_analysis",
        }
        self.assertEqual(
            {key: value[0] for key, value in self.catalog.items()},
            expected,
        )
        self.assertEqual(len(set(expected.values())), len(expected))
        for key, (_, title, detail, status) in self.catalog.items():
            with self.subTest(check=key):
                self.assertTrue(title)
                self.assertTrue(detail)
                self.assertEqual(
                    status,
                    "current" if key in (
                        "clamav", "signatures", "integrity", "handoff"
                    ) else "planned",
                )

    def test_all_three_levels_match_structured_required_and_optional_policy(self):
        for profile in ProtectionProfileID:
            with self.subTest(level=profile.value):
                policy = PROTECTION_POLICIES[profile]
                for property_name, requirements in (
                    ("requiredChecks", policy.required_checks),
                    ("optionalChecks", policy.optional_checks),
                ):
                    keys = self._level_keys(property_name, profile.value)
                    actual = {
                        self.catalog[key][0]: self.catalog[key][3]
                        for key in keys
                    }
                    expected = {
                        entry.control.value: entry.availability.value
                        for entry in requirements
                    }
                    self.assertEqual(len(keys), len(set(keys)))
                    self.assertEqual(actual, expected)
                self.assertFalse(policy.selectable)
        self.assertEqual(self._level_keys("optionalChecks", "maximum"), [])

    def test_each_card_displays_the_checks_and_optional_labels(self):
        for required in (
            'Text("Required checks: \\(tier.requiredChecks.map(\\.title).joined(separator: ", "))")',
            'Text("Optional planned checks: \\(tier.optionalChecks.map(\\.title).joined(separator: ", "))")',
            "if !tier.optionalChecks.isEmpty",
            "ForEach(PlannedProtectionTier.allCases)",
            "ForEach(selectedPreview.requiredChecks)",
            "ForEach(selectedPreview.optionalChecks)",
            'Text("Required checks")',
            'Text("Optional planned checks")',
            'Text(check.availability.rawValue)',
            "Current Built-in safeguard",
            "Planned; not active",
            'accessibilityIdentifier("protectionCheck-\\(check.id)")',
            ".accessibilityElement(children: .combine)",
            ".fixedSize(horizontal: false, vertical: true)",
        ):
            with self.subTest(required=required):
                self.assertIn(required, self.swift)
        self.assertIn("only the current Built-in safeguards are enforced", self.swift)

    def test_previews_do_not_change_policy_or_saved_settings(self):
        from protection_profiles import PROTECTION_PROFILES
        self.assertTrue(all(not tier.selectable for tier in PROTECTION_PROFILES.values()))
        self.assertIn("selectedPreview = tier", self.swift)
        self.assertIn("Active protection: Built-in ClamAV", self.swift)
        self.assertIn("Preview only · Not available as an active policy", self.swift)
        for forbidden in (
            "UserDefaults", "@AppStorage", "FileManager", "Process(",
            "NSWorkspace", "URLSession", "SelectedProtectionProfilePreference",
            "scan-and-open", "target-app.txt", "Toggle(", "Picker(", "save(",
        ):
            with self.subTest(forbidden=forbidden):
                self.assertNotIn(forbidden, self.swift)

    def test_existing_protection_sections_and_native_ci_remain(self):
        for name in (
            'GroupBox("Malware scanning")',
            'GroupBox("Unsafe or unverified files")',
            'GroupBox("Verified application handoff")',
            'accessibilityIdentifier("protectionCardPreviewDetail")',
        ):
            self.assertIn(name, self.swift)
        self.assertIn("macos-build:", CI.read_text(encoding="utf-8"))
        self.assertIn(
            "python3 test-protection-settings-checks.py -v",
            CI.read_text(encoding="utf-8"),
        )
        self.assertIn(
            "path = ProtectionSettingsView.swift;",
            (ROOT / "PDFMagicOpener.xcodeproj" / "project.pbxproj").read_text(),
        )
        gate = (ROOT / "scan-and-open.py").read_text(encoding="utf-8")
        self.assertNotIn("ProtectionLevelCheckCatalog", gate)


if __name__ == "__main__":
    unittest.main()
