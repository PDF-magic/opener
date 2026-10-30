#!/usr/bin/env python3
"""opener-0341: inspect the exact enforced policy, never an inactive preview."""

import json
from pathlib import Path
import re
import unittest

from effective_protection_policy import (
    ACTIVE_PROFILE_ID, SELECTED_PROFILE_KEY, UnsupportedEffectivePolicy,
    resolve_effective_policy,
)
from protection_policy_definitions import BASELINE_CONTROLS, FailureDisposition
from protection_profiles import PROTECTION_PROFILES

ROOT = Path(__file__).resolve().parent
VIEW = ROOT / "PDFMagicOpenerApp" / "ProtectionSettingsView.swift"
SOURCE = VIEW.read_text(encoding="utf-8")


def displayed_policy_document():
    """Read the verbatim, read-only JSON displayed to users in the disclosure."""
    matches = re.findall(
        r'private enum ExactEffectiveScanPolicy\s*\{\s*'
        r'static let json = """(.*?)"""',
        SOURCE, flags=re.DOTALL,
    )
    if len(matches) != 1:
        raise AssertionError("Exactly one exact effective policy contract is required")
    return json.loads(matches[0])


class EffectivePolicyDisplayTests(unittest.TestCase):
    def test_displayed_policy_is_exactly_the_enforced_resolver_contract(self):
        actual = resolve_effective_policy()
        displayed = displayed_policy_document()
        self.assertEqual(
            set(displayed),
            {"profile_id", "required_checks", "optional_checks", "failure_disposition"},
        )
        self.assertEqual(displayed["profile_id"], actual.profile_id)
        self.assertEqual(
            displayed["required_checks"],
            [check.value for check in BASELINE_CONTROLS],
        )
        self.assertEqual(set(displayed["required_checks"]), {
            check.value for check in actual.required_checks
        })
        self.assertEqual(displayed["optional_checks"], sorted(
            check.value for check in actual.optional_checks
        ))
        self.assertEqual(displayed["failure_disposition"], actual.failure_disposition.value)
        self.assertEqual(actual.failure_disposition, FailureDisposition.DENY)
        self.assertEqual(actual.profile_id, ACTIVE_PROFILE_ID)

    def test_disclosure_is_an_actual_read_only_user_option(self):
        for required in (
            '@State private var showExactEffectivePolicy = false',
            'DisclosureGroup(isExpanded: $showExactEffectivePolicy)',
            'Text("View exact effective scan policy")',
            'Text(ExactEffectiveScanPolicy.json)',
            '.textSelection(.enabled)',
            'accessibilityIdentifier("viewExactEffectiveScanPolicy")',
            'accessibilityIdentifier("exactEffectiveScanPolicyJSON")',
            '.accessibilityHint("Expand to read the current enforced policy as JSON;',
            'accessibilityIdentifier("activeBuiltInProtection")',
            'accessibilityIdentifier("plannedProtectionCardsSection")',
            'This policy description does not report a particular file',
            'Scanner-owned timeouts may be tightened per request.',
        ):
            with self.subTest(marker=required):
                self.assertIn(required, SOURCE)
        self.assertLess(
            SOURCE.index('accessibilityIdentifier("activeBuiltInProtection")'),
            SOURCE.index('DisclosureGroup(isExpanded: $showExactEffectivePolicy)'),
        )
        self.assertLess(
            SOURCE.index('DisclosureGroup(isExpanded: $showExactEffectivePolicy)'),
            SOURCE.index('GroupBox("Planned protection levels")'),
        )

    def test_disclosure_cannot_override_scans_or_modify_preferences(self):
        first = SOURCE.index('DisclosureGroup(isExpanded: $showExactEffectivePolicy)')
        last = SOURCE.index('accessibilityHint("Expand to read the current enforced policy')
        disclosure = SOURCE[first:last]
        for forbidden in (
            "Button(", "Process(", "UserDefaults", "@AppStorage", "FileManager",
            "scan_and_open", "launch_clean_file", "NSWorkspace", "saveExplicitChoice",
            "clamscan", "URLSession", "onOpenURL", "setDefault", "Toggle(",
        ):
            with self.subTest(forbidden=forbidden):
                self.assertNotIn(forbidden, disclosure)
        scanner = (ROOT / "scan-and-open.py").read_text(encoding="utf-8")
        self.assertNotIn("ExactEffectiveScanPolicy", scanner)
        self.assertIn("if not cached_clean(cache_id):", scanner)

    def test_planned_tiers_or_saved_previews_cannot_change_the_display(self):
        policy = displayed_policy_document()
        self.assertEqual(policy["profile_id"], "built-in")
        self.assertEqual(policy["optional_checks"], [])
        self.assertTrue(all(not tier.selectable for tier in PROTECTION_PROFILES.values()))
        for level in ("standard", "enhanced", "maximum"):
            self.assertNotIn(level, policy["required_checks"])
            with self.subTest(planned=level):
                with self.assertRaises(UnsupportedEffectivePolicy):
                    resolve_effective_policy({SELECTED_PROFILE_KEY: level})
                self.assertEqual(displayed_policy_document(), policy)
        self.assertEqual(
            resolve_effective_policy({"customBrowser": "my own", "showScanProgress": False}),
            resolve_effective_policy(),
        )
        self.assertIn("PlannedProtectionLevelPreference.selected()", SOURCE)

    def test_native_build_includes_protection_view_and_no_new_scanner_dependency(self):
        project = (ROOT / "PDFMagicOpener.xcodeproj/project.pbxproj").read_text()
        ci = (ROOT / ".github/workflows/ci.yml").read_text()
        self.assertIn("path = ProtectionSettingsView.swift;", project)
        self.assertIn("macos-build:", ci)
        self.assertIn("Text(ExactEffectiveScanPolicy.json)", SOURCE)


if __name__ == "__main__":
    unittest.main()
