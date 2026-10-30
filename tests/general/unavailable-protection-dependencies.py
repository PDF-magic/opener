#!/usr/bin/env python3
"""opener-0338: unavailable mandatory engines block effective profile selection."""

from pathlib import Path
import unittest

from effective_protection_policy import (
    ACTIVE_PROFILE_ID, SELECTED_PROFILE_KEY, UnsupportedEffectivePolicy,
    resolve_effective_policy,
)
from protection_policy_definitions import (
    ControlAvailability, PROTECTION_POLICIES, PolicyControl,
)
from protection_profiles import PROTECTION_PROFILES, ProtectionProfileID

ROOT = Path(__file__).resolve().parent
VIEW = ROOT / "PDFMagicOpenerApp" / "ProtectionSettingsView.swift"


class UnavailableProtectionDependenciesTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source = VIEW.read_text(encoding="utf-8")

    def test_every_unavailable_mandatory_engine_is_named(self):
        planned_required = {
            tier.value: {
                requirement.control
                for requirement in PROTECTION_POLICIES[tier].required_checks
                if requirement.availability is ControlAvailability.PLANNED
            }
            for tier in ProtectionProfileID
        }
        self.assertEqual(planned_required, {
            "standard": set(),
            "enhanced": {PolicyControl.PDF_STRUCTURE_VALIDATION},
            "maximum": {
                PolicyControl.PDF_STRUCTURE_VALIDATION,
                PolicyControl.ISOLATED_BEHAVIOR_ANALYSIS,
            },
        })
        view = self.source
        self.assertIn("var unavailableMandatoryChecks: [ProtectionLevelCheck]", view)
        self.assertIn("requiredChecks.filter { $0.availability == .planned }", view)
        for profile, required in planned_required.items():
            with self.subTest(profile=profile):
                self.assertIn(f"case .{profile}:", view)
                for mandatory in required:
                    label = {
                        PolicyControl.PDF_STRUCTURE_VALIDATION: "PDF structure validation",
                        PolicyControl.ISOLATED_BEHAVIOR_ANALYSIS: "isolated behavior analysis",
                    }[mandatory]
                    self.assertIn(label, view)
        self.assertIn('Text("Unavailable mandatory engines")', view)
        self.assertIn("ForEach(selectedPreview.unavailableMandatoryChecks)", view)

    def test_activation_unavailable_is_explained_for_all_levels(self):
        source = self.source
        for phrase in (
            "Standard activation unavailable: the named Standard policy",
            "Enhanced activation unavailable: required PDF structure validation",
            "Maximum activation unavailable: required PDF structure validation and isolated behavior analysis",
            "not integrated as mandatory scan engines",
            "not a live test of installed scanner binaries",
            "A missing mandatory engine never enables selection.",
            "profileActivationBlockedReason",
            "Text(tier.activationBlockReason)",
            "Text(selectedPreview.activationBlockReason)",
        ):
            with self.subTest(phrase=phrase):
                self.assertIn(phrase, source)
        self.assertIn("Built-in ClamAV policy remains active", source)
        self.assertIn("Preview only · Not available as an active policy", source)

    def test_planned_profiles_cannot_become_effective_when_required_engine_missing(self):
        for tier in ProtectionProfileID:
            with self.subTest(tier=tier.value):
                self.assertFalse(PROTECTION_PROFILES[tier].selectable)
                self.assertFalse(PROTECTION_POLICIES[tier].selectable)
                with self.assertRaises(UnsupportedEffectivePolicy):
                    resolve_effective_policy({SELECTED_PROFILE_KEY: tier.value})
        self.assertEqual(resolve_effective_policy().profile_id, ACTIVE_PROFILE_ID)
        self.assertEqual(
            resolve_effective_policy({SELECTED_PROFILE_KEY: ACTIVE_PROFILE_ID}).profile_id,
            ACTIVE_PROFILE_ID,
        )
        with self.assertRaises(UnsupportedEffectivePolicy):
            resolve_effective_policy({SELECTED_PROFILE_KEY: "enhanced"})

    def test_preview_controls_stay_available_but_cannot_persist_active_choice(self):
        source = self.source
        self.assertIn("selectedPreview = tier", source)
        self.assertIn("selectedPreview == tier", source)
        self.assertIn('accessibilityIdentifier("protectionCard-\\(tier.rawValue)")', source)
        self.assertIn("Activation stays blocked while mandatory engines are unavailable.", source)
        # op. 0336 persists the preview choice only, never an effective
        # selection. A restored highlight is still not an active scan tier.
        self.assertIn("PlannedProtectionLevelPreference.saveExplicitChoice(level)", source)
        self.assertIn("PlannedProtectionLevelPreference.selected()", source)
        self.assertIn("PreferredProtectionLevel(rawValue: tier.rawValue)", source)
        for forbidden in (
            "UserDefaults", "@AppStorage", "SelectedProtectionProfilePreference",
            "FileManager", "Process(", "NSWorkspace", "URLSession",
            "scan-and-open", "clamscan(", "write(to:",
        ):
            with self.subTest(forbidden=forbidden):
                self.assertNotIn(forbidden, source)
        original = (ROOT / "scan-and-open.py").read_text(encoding="utf-8")
        self.assertIn("if not cached_clean(cache_id):", original)
        self.assertNotIn("activationBlockReason", original)

    def test_regressions_and_native_target_run_in_ci(self):
        ci = (ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")
        self.assertIn("python3 test-unavailable-protection-dependencies.py -v", ci)
        self.assertIn("python3 test-protection-settings-cards.py -v", ci)
        self.assertIn("python3 test-protection-settings-checks.py -v", ci)
        self.assertIn("python3 test-missing-dependency-policy.py -v", ci)
        self.assertIn("macos-build:", ci)
        self.assertIn("path = ProtectionSettingsView.swift;", (
            ROOT / "PDFMagicOpener.xcodeproj" / "project.pbxproj"
        ).read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
