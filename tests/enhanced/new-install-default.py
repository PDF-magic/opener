#!/usr/bin/env python3
"""opener-0333: evidence-gated Enhanced new-install default recommendation.

A planned protection tier must not be called a recommended default merely
because its non-executable components have unit tests or preview cards.
"""

from pathlib import Path
import re
import unittest

from effective_protection_policy import (
    ACTIVE_PROFILE_ID, SELECTED_PROFILE_KEY,
    UnsupportedEffectivePolicy, resolve_effective_policy,
)
from protection_policy_definitions import (
    ControlAvailability, PROTECTION_POLICIES,
)
from protection_profiles import PROTECTION_PROFILES, ProtectionProfileID

ROOT = Path(__file__).resolve().parents[2]
VIEW = ROOT / "PDFMagicOpenerApp" / "ProtectionSettingsView.swift"
SCANNER = ROOT / "scan-and-open.py"


class EnhancedNewInstallRecommendationTests(unittest.TestCase):
    def setUp(self):
        self.view = VIEW.read_text(encoding="utf-8")

    def test_current_evidence_cannot_justify_enhanced_as_the_default(self):
        enhanced = PROTECTION_PROFILES[ProtectionProfileID.ENHANCED]
        policy = PROTECTION_POLICIES[ProtectionProfileID.ENHANCED]
        self.assertFalse(enhanced.selectable)
        self.assertFalse(policy.selectable)
        self.assertTrue(any(
            check.availability is ControlAvailability.PLANNED
            for check in (*policy.required_checks, *policy.optional_checks)
        ))
        self.assertEqual(resolve_effective_policy().profile_id, ACTIVE_PROFILE_ID)
        self.assertEqual(ACTIVE_PROFILE_ID, "built-in")
        with self.assertRaises(UnsupportedEffectivePolicy):
            resolve_effective_policy({SELECTED_PROFILE_KEY: "enhanced"})

    def test_preference_view_identifies_conditional_candidate_without_false_badge(self):
        for required in (
            'GroupBox("New installation recommendation")',
            'Enhanced: not yet recommended as a new-install default',
            "only if testing demonstrates",
            "full safety checks are implemented",
            "fail closed",
            "acceptable measured performance",
            "no end-to-end comparison establishes a safe default",
            "New installations retain Built-in ClamAV scanning.",
            '.accessibilityIdentifier("enhancedNewInstallRecommendationStatus")',
        ):
            with self.subTest(required=required):
                self.assertIn(required, self.view)
        self.assertNotIn('Text("Enhanced: recommended default")', self.view)
        self.assertNotIn("Recommended default for new installations", self.view)

    def test_recommendation_is_informational_not_a_new_activation_control(self):
        start = self.view.index('GroupBox("New installation recommendation")')
        end = self.view.index('GroupBox("Planned protection levels")', start)
        section = self.view[start:end]
        self.assertIn("VStack", section)
        self.assertNotIn("Button", section)
        self.assertNotIn("Toggle", section)
        self.assertNotIn("Picker", section)
        self.assertNotIn("UserDefaults", section)
        self.assertNotIn("@AppStorage", section)
        self.assertNotIn("selectedPreview =", section)
        self.assertNotIn("save(", section)
        self.assertNotIn("Process(", section)
        self.assertNotIn("FileManager", section)
        self.assertNotIn("onAppear", section)
        self.assertIn('Active protection: Built-in ClamAV scanning', self.view)
        self.assertIn("Preview only · Not available as an active policy", self.view)

    def test_installer_and_saved_preferences_are_not_modified(self):
        # This PR is strictly an explanatory status in Preferences. The
        # effective policy and existing user selections are not mutated.
        from protection_profiles import BASELINE_SAFETY_CHECKS
        self.assertEqual(
            frozenset(BASELINE_SAFETY_CHECKS),
            frozenset({
                "clamav_scan_gate", "signature_freshness",
                "file_integrity", "fail_closed_handoff",
            }),
        )
        scanner = SCANNER.read_text(encoding="utf-8")
        self.assertIn("if not cached_clean(cache_id):", scanner)
        self.assertNotIn("New installation recommendation", scanner)
        config_test = (ROOT / "test-policy-settings-upgrade.swift").read_text(
            encoding="utf-8"
        )
        self.assertIn("built-in", config_test)
        self.assertFalse(PROTECTION_PROFILES[ProtectionProfileID.STANDARD].selectable)

    def test_existing_previews_and_accessible_labels_remain_unchanged(self):
        for marker in (
            'ForEach(PlannedProtectionTier.allCases)',
            '.accessibilityIdentifier("plannedProtectionCardsSection")',
            '.accessibilityIdentifier("activeBuiltInProtection")',
            'selectedPreview = tier',
            'selectedPreview == tier',
        ):
            self.assertIn(marker, self.view)

    def test_ci_runs_portable_evidence_guard_on_ubuntu_and_keeps_native_build(self):
        workflow = (ROOT / ".github/workflows/consolidated-checks.yml").read_text(
            encoding="utf-8"
        )
        portable = workflow.split("  macos-native-tests:", 1)[0]
        native = workflow.split("  macos-native-tests:", 1)[1]
        self.assertIn("tests/enhanced/new-install-default.py -v", portable)
        self.assertIn("ubuntu-latest", portable)
        self.assertNotIn("tests/enhanced/new-install-default.py -v", native)
        ci = (ROOT / ".github/workflows/ci.yml").read_text(encoding="utf-8")
        self.assertIn("macos-build:", ci)


if __name__ == "__main__":
    unittest.main()
