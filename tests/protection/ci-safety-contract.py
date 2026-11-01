#!/usr/bin/env python3
"""CI contract for the active security floor and inactive protection previews."""

from dataclasses import replace
from types import MappingProxyType
import unittest

from effective_protection_policy import (
    ACTIVE_PROFILE_ID,
    SELECTED_PROFILE_KEY,
    UnsupportedEffectivePolicy,
    resolve_effective_policy,
)
from protection_policy_definitions import (
    ControlAvailability,
    FailureDisposition,
    PolicyControl,
    PROTECTION_POLICIES,
    protection_policy_definition,
)
from protection_profiles import BASELINE_SAFETY_CHECKS, ProtectionProfileID


CURRENT = {
    "clamav_scan_gate",
    "signature_freshness",
    "file_integrity",
    "fail_closed_handoff",
}
EXPECTED = {
    ProtectionProfileID.STANDARD: (
        CURRENT, {"pdf_structure_validation"},
        set(),
    ),
    ProtectionProfileID.ENHANCED: (
        CURRENT | {"pdf_structure_validation"},
        {"isolated_behavior_analysis"},
        {"pdf_structure_validation"},
    ),
    ProtectionProfileID.MAXIMUM: (
        CURRENT | {"pdf_structure_validation", "isolated_behavior_analysis"},
        set(),
        {"pdf_structure_validation", "isolated_behavior_analysis"},
    ),
}


class ProtectionPolicyCIContractTests(unittest.TestCase):
    def test_every_planned_tier_preserves_the_exact_active_floor(self):
        self.assertEqual(BASELINE_SAFETY_CHECKS, frozenset(CURRENT))
        self.assertEqual(set(PROTECTION_POLICIES), set(EXPECTED))
        for profile, (required, optional, planned) in EXPECTED.items():
            with self.subTest(profile=profile.value):
                policy = protection_policy_definition(profile)
                current = {
                    item.control.value for item in policy.requirements
                    if item.availability is ControlAvailability.CURRENT
                }
                required_values = {item.control.value for item in policy.requirements}
                optional_values = {item.control.value for item in policy.optional_checks}
                planned_values = {
                    item.control.value for item in policy.requirements
                    if item.availability is ControlAvailability.PLANNED
                }
                self.assertEqual(current, CURRENT)
                self.assertEqual(required_values, required)
                self.assertEqual(optional_values, optional)
                self.assertEqual(planned_values, planned)
                self.assertTrue(all(item.availability is ControlAvailability.PLANNED
                                    for item in policy.optional_checks))
                self.assertIs(policy.failure_disposition, FailureDisposition.DENY)
                self.assertFalse(policy.selectable)
                document = policy.as_document()
                self.assertEqual(document["failure_disposition"], "deny")
                self.assertFalse(document["selectable"])

    def test_each_tier_rejects_missing_scan_gate_or_attempted_activation(self):
        for profile, policy in PROTECTION_POLICIES.items():
            with self.subTest(profile=profile.value):
                reduced = tuple(
                    item for item in policy.requirements
                    if item.control is not PolicyControl.CLAMAV_SCAN_GATE
                )
                with self.assertRaises(ValueError):
                    replace(policy, requirements=reduced)
                with self.assertRaises(ValueError):
                    replace(policy, selectable=True)
                with self.assertRaises(ValueError):
                    replace(policy, failure_disposition="allow")
                with self.assertRaises(ValueError):
                    replace(policy, optional_checks=policy.optional_checks + (
                        policy.requirements[0],
                    ))

    def test_saved_customizations_never_change_the_deployed_policy(self):
        active = resolve_effective_policy()
        self.assertEqual(active.profile_id, ACTIVE_PROFILE_ID)
        self.assertEqual(active.required_checks,
                         frozenset(PolicyControl(key) for key in CURRENT))
        self.assertEqual(active.optional_checks, frozenset())
        self.assertIs(active.failure_disposition, FailureDisposition.DENY)
        for preferences in (
            {},
            {"customBrowser": "preferred-app", "showScanProgress": False},
            {SELECTED_PROFILE_KEY: ACTIVE_PROFILE_ID,
             "showSuccessfulScanNotifications": True},
            MappingProxyType({SELECTED_PROFILE_KEY: ACTIVE_PROFILE_ID,
                              "customBrowser": "unchanged"}),
        ):
            with self.subTest(preferences=repr(preferences)):
                original = dict(preferences)
                self.assertIs(resolve_effective_policy(preferences), active)
                self.assertEqual(dict(preferences), original)

    def test_planned_and_malformed_profile_choices_fail_closed(self):
        for choice in (
            *(profile.value for profile in ProtectionProfileID),
            *ProtectionProfileID,
            "disabled", "", None, False, 0, "Built-in",
        ):
            with self.subTest(choice=repr(choice)):
                settings = {SELECTED_PROFILE_KEY: choice,
                            "customBrowser": "preserve-me"}
                original = dict(settings)
                with self.assertRaises(UnsupportedEffectivePolicy):
                    resolve_effective_policy(settings)
                self.assertEqual(settings, original)


if __name__ == "__main__":
    unittest.main()
