#!/usr/bin/env python3
"""Contract for explicitly required and optional planned checks (opener-0251)."""

from dataclasses import FrozenInstanceError
import json
from pathlib import Path
import unittest

from protection_profiles import BASELINE_SAFETY_CHECKS, ProtectionProfileID
from protection_policy_definitions import (
    BASELINE_CONTROLS,
    OPTIONAL_CHECKS_BY_PROFILE,
    PROTECTION_POLICIES,
    REQUIRED_CHECKS_BY_PROFILE,
    ControlAvailability,
    FailureDisposition,
    PolicyControl,
    PolicyRequirement,
    StructuredProtectionPolicy,
    protection_policy_definition,
)

ROOT = Path(__file__).resolve().parents[2]


class ProfileCheckAssignmentsTests(unittest.TestCase):
    def test_exact_per_profile_required_and_optional_checks(self):
        baseline = frozenset(BASELINE_CONTROLS)
        structure = PolicyControl.PDF_STRUCTURE_VALIDATION
        behavior = PolicyControl.ISOLATED_BEHAVIOR_ANALYSIS
        expected = {
            ProtectionProfileID.STANDARD: (baseline, frozenset({structure})),
            ProtectionProfileID.ENHANCED: (baseline | {structure}, frozenset({behavior})),
            ProtectionProfileID.MAXIMUM: (baseline | {structure, behavior}, frozenset()),
        }
        self.assertEqual(set(PROTECTION_POLICIES), set(expected))
        self.assertEqual(set(REQUIRED_CHECKS_BY_PROFILE), set(expected))
        self.assertEqual(set(OPTIONAL_CHECKS_BY_PROFILE), set(expected))
        for profile, (required, optional) in expected.items():
            with self.subTest(profile=profile.value):
                policy = protection_policy_definition(profile)
                self.assertEqual(REQUIRED_CHECKS_BY_PROFILE[profile], required)
                self.assertEqual(OPTIONAL_CHECKS_BY_PROFILE[profile], optional)
                self.assertEqual({r.control for r in policy.required_checks}, required)
                self.assertEqual({r.control for r in policy.optional_checks}, optional)
                self.assertFalse(required & optional)
                self.assertTrue(baseline <= required)
                self.assertFalse(policy.selectable)
                self.assertIs(policy.failure_disposition, FailureDisposition.DENY)
                for item in policy.required_checks:
                    expected_availability = (ControlAvailability.CURRENT
                        if item.control in baseline else ControlAvailability.PLANNED)
                    self.assertIs(item.availability, expected_availability)
                for item in policy.optional_checks:
                    self.assertIs(item.availability, ControlAvailability.PLANNED)
                    self.assertNotIn(item.control, baseline)
        self.assertEqual(frozenset(control.value for control in baseline),
                         BASELINE_SAFETY_CHECKS)

    def test_optional_entries_are_explicit_json_metadata_not_activation(self):
        for profile in ProtectionProfileID:
            policy = protection_policy_definition(profile)
            document = json.loads(json.dumps(policy.as_document()))
            self.assertEqual(document["profile_id"], profile.value)
            self.assertEqual(document["failure_disposition"], "deny")
            self.assertFalse(document["selectable"])
            self.assertEqual(
                {item["control"] for item in document["requirements"]},
                {item.control.value for item in policy.required_checks})
            self.assertEqual(
                {item["control"] for item in document["optional_checks"]},
                {item.control.value for item in policy.optional_checks})
            self.assertTrue(all(item["availability"] == "planned"
                                for item in document["optional_checks"]))
            document["optional_checks"].clear()
            self.assertEqual(
                {item.control.value for item in policy.optional_checks},
                {item.value for item in OPTIONAL_CHECKS_BY_PROFILE[profile]})

    def test_missing_duplicate_weakened_or_misclassified_checks_are_rejected(self):
        standard = protection_policy_definition(ProtectionProfileID.STANDARD)
        base = dict(profile_id=standard.profile_id, requirements=standard.requirements,
                    optional_checks=standard.optional_checks)
        baseline = PolicyRequirement(PolicyControl.CLAMAV_SCAN_GATE,
                                     ControlAvailability.CURRENT)
        structure = PolicyRequirement(PolicyControl.PDF_STRUCTURE_VALIDATION,
                                      ControlAvailability.PLANNED)
        invalid = (
            {"optional_checks": ()},  # Silent omission loses the explicit optional definition.
            {"requirements": standard.requirements[:-1]},  # Mandatory floor removed.
            {"optional_checks": (baseline,)},  # A mandatory gate is never optional.
            {"optional_checks": (structure, structure)},  # Duplicate optional controls.
            {"optional_checks": (PolicyRequirement(
                PolicyControl.PDF_STRUCTURE_VALIDATION, ControlAvailability.CURRENT),)},
            {"requirements": standard.requirements + (structure,)},  # Overlap.
            {"optional_checks": (PolicyRequirement(
                PolicyControl.ISOLATED_BEHAVIOR_ANALYSIS, ControlAvailability.PLANNED),)},
            {"optional_checks": [structure]},  # Mutable collection.
            {"optional_checks": ("pdf_structure_validation",)},  # Unvalidated control.
            {"selectable": True},
            {"failure_disposition": "allow"},
        )
        for changes in invalid:
            with self.subTest(changes=changes), self.assertRaises((ValueError, TypeError)):
                StructuredProtectionPolicy(**{**base, **changes})
        for registry in (REQUIRED_CHECKS_BY_PROFILE, OPTIONAL_CHECKS_BY_PROFILE):
            with self.assertRaises(TypeError):
                registry[ProtectionProfileID.STANDARD] = frozenset()
        with self.assertRaises(FrozenInstanceError):
            standard.optional_checks = ()
        with self.assertRaises(FrozenInstanceError):
            standard.optional_checks[0].availability = ControlAvailability.CURRENT

    def test_definition_is_non_executable_and_preserves_scanner_policy(self):
        scanner = (ROOT / "scan-and-open.py").read_text(encoding="utf-8")
        policy_source = (ROOT / "protection_policy_definitions.py").read_text(encoding="utf-8")
        self.assertNotIn("protection_policy_definitions", scanner)
        self.assertIn("if not cached_clean(cache_id):", scanner)
        self.assertNotIn("UserDefaults", policy_source)
        self.assertNotIn("subprocess.run", policy_source)
        self.assertNotIn("def apply_policy", policy_source)
        self.assertNotIn("def select_profile", policy_source)
        self.assertIn('static let name = "Built-in"',
                      (ROOT / "scan-progress-view.swift").read_text(encoding="utf-8"))
        self.assertIn("python3 tests/general/required-optional-profile-checks.py -v",
                      (ROOT / ".github/workflows/ci.yml").read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
