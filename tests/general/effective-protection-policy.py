#!/usr/bin/env python3
"""opener-0260: one safe resolver for the installed effective policy."""

from dataclasses import FrozenInstanceError
from pathlib import Path
from types import MappingProxyType
import unittest

from effective_protection_policy import (
    ACTIVE_PROFILE_ID,
    SELECTED_PROFILE_KEY,
    EffectiveProtectionPolicy,
    UnsupportedEffectivePolicy,
    resolve_effective_policy,
)
from protection_policy_definitions import (
    BASELINE_CONTROLS,
    ControlAvailability,
    FailureDisposition,
    PolicyControl,
    PROTECTION_POLICIES,
)
from protection_profiles import BASELINE_SAFETY_CHECKS, ProtectionProfileID

ROOT = Path(__file__).resolve().parent


class EffectivePolicyResolutionTests(unittest.TestCase):
    def test_missing_and_explicit_built_in_resolve_identically(self):
        missing = resolve_effective_policy()
        self.assertIs(missing, resolve_effective_policy({}))
        self.assertIs(missing, resolve_effective_policy({
            "showScanProgress": False, "customBrowser": "preserved",
        }))
        self.assertIs(missing, resolve_effective_policy({
            SELECTED_PROFILE_KEY: ACTIVE_PROFILE_ID,
        }))
        self.assertIs(missing, resolve_effective_policy(MappingProxyType({
            SELECTED_PROFILE_KEY: ACTIVE_PROFILE_ID,
            "showSuccessfulScanNotifications": True,
        })))
        self.assertEqual(missing.profile_id, "built-in")

    def test_mandatory_floor_is_complete_and_never_optional(self):
        policy = resolve_effective_policy({"showScanProgress": False})
        self.assertEqual(policy.required_checks, frozenset(BASELINE_CONTROLS))
        self.assertEqual(
            frozenset(control.value for control in policy.required_checks),
            BASELINE_SAFETY_CHECKS,
        )
        self.assertEqual(len(policy.required_checks), 4)
        self.assertEqual(policy.optional_checks, frozenset())
        self.assertIs(policy.failure_disposition, FailureDisposition.DENY)
        self.assertEqual(
            {r.availability for r in PROTECTION_POLICIES[ProtectionProfileID.STANDARD].requirements},
            {ControlAvailability.CURRENT},
        )

    def test_unimplemented_planned_or_corrupt_selection_never_falls_back(self):
        for selection in (
            "standard", "enhanced", "maximum", "disabled", "", "BUILT-IN",
            "built-in ", None, False, True, 0, 1, [], {"profile": "built-in"},
        ):
            with self.subTest(selection=repr(selection)):
                with self.assertRaises(UnsupportedEffectivePolicy):
                    resolve_effective_policy({SELECTED_PROFILE_KEY: selection})
        for profile in ProtectionProfileID:
            with self.subTest(planned=profile.value):
                with self.assertRaises(UnsupportedEffectivePolicy):
                    resolve_effective_policy({SELECTED_PROFILE_KEY: profile})

    def test_nonmapping_input_is_rejected(self):
        for value in (False, "", "built-in", [], 1):
            with self.subTest(value=repr(value)), self.assertRaises(TypeError):
                resolve_effective_policy(value)

    def test_weaker_or_mutable_effective_policy_cannot_be_constructed(self):
        policy = resolve_effective_policy()
        required = frozenset(BASELINE_CONTROLS)
        cases = (
            {"required_checks": required - {PolicyControl.CLAMAV_SCAN_GATE}},
            {"required_checks": required - {PolicyControl.SIGNATURE_FRESHNESS}},
            {"required_checks": required - {PolicyControl.FILE_INTEGRITY}},
            {"required_checks": required - {PolicyControl.FAIL_CLOSED_HANDOFF}},
            {"required_checks": set(required)},
            {"failure_disposition": "allow"},
            {"profile_id": "standard"},
            {"optional_checks": frozenset({PolicyControl.PDF_STRUCTURE_VALIDATION})},
            {"optional_checks": {PolicyControl.PDF_STRUCTURE_VALIDATION}},
        )
        base = {
            "profile_id": policy.profile_id,
            "required_checks": required,
            "failure_disposition": FailureDisposition.DENY,
        }
        for changes in cases:
            with self.subTest(changes=repr(changes)):
                with self.assertRaises(UnsupportedEffectivePolicy):
                    EffectiveProtectionPolicy(**{**base, **changes})
        with self.assertRaises(FrozenInstanceError):
            policy.profile_id = "standard"
        with self.assertRaises(FrozenInstanceError):
            policy.required_checks = frozenset()
        with self.assertRaises(AttributeError):
            policy.required_checks.add(PolicyControl.PDF_STRUCTURE_VALIDATION)

    def test_read_only_and_unrelated_customizations_are_not_changed(self):
        saved = {
            SELECTED_PROFILE_KEY: "built-in",
            "showScanProgress": False,
            "customBrowser": "user-choice",
            "overrideMandatoryChecks": False,
        }
        snapshot = dict(saved)
        policy = resolve_effective_policy(saved)
        self.assertEqual(saved, snapshot)
        self.assertIs(policy, resolve_effective_policy())
        self.assertEqual(policy.required_checks, frozenset(BASELINE_CONTROLS))

        # Neither this resolver nor its tests may replace the scanner gate.
        source = (ROOT / "effective_protection_policy.py").read_text()
        scanner = (ROOT / "scan-and-open.py").read_text()
        self.assertNotIn("effective_protection_policy", scanner)
        for forbidden in ("subprocess", "open(", "write_text(", "UserDefaults", "remove_quarantine", "launch_clean_file"):
            self.assertNotIn(forbidden, source)


if __name__ == "__main__":
    unittest.main()
