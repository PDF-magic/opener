#!/usr/bin/env python3
"""Regression checks for Maximum's inheritance of every Enhanced requirement."""

from dataclasses import FrozenInstanceError
from pathlib import Path
import json
import unittest

from protection_profiles import ProtectionProfileID
from protection_policy_definitions import (
    BASELINE_CONTROLS, ControlAvailability, FailureDisposition,
    OPTIONAL_CHECKS_BY_PROFILE, PolicyControl, PolicyRequirement,
    PROTECTION_POLICIES, REQUIRED_CHECKS_BY_PROFILE, StructuredProtectionPolicy,
    _inherit_enhanced_requirements,
)
from protection_stage_resource_budgets import resource_budgets_for_profile
from protection_stage_time_limits import stage_limits_for_profile
from effective_protection_policy import (
    SELECTED_PROFILE_KEY, UnsupportedEffectivePolicy, resolve_effective_policy,
)

ROOT = Path(__file__).resolve().parent


class MaximumInheritsEnhancedRequirementsTests(unittest.TestCase):
    def setUp(self):
        self.enhanced = PROTECTION_POLICIES[ProtectionProfileID.ENHANCED]
        self.maximum = PROTECTION_POLICIES[ProtectionProfileID.MAXIMUM]

    def test_maximum_inherits_every_enhanced_requirement_with_availability(self):
        expected = {entry.control: entry.availability for entry in self.enhanced.requirements}
        actual = {entry.control: entry.availability for entry in self.maximum.requirements}
        self.assertEqual(len(actual), len(self.maximum.requirements))
        self.assertTrue(expected.items() <= actual.items())
        self.assertTrue(set(BASELINE_CONTROLS) <= set(actual))
        self.assertEqual(set(REQUIRED_CHECKS_BY_PROFILE[ProtectionProfileID.ENHANCED]),
                         set(expected))
        self.assertEqual(set(REQUIRED_CHECKS_BY_PROFILE[ProtectionProfileID.MAXIMUM]),
                         set(actual))
        self.assertIs(self.maximum.failure_disposition, FailureDisposition.DENY)

    def test_enhanced_optional_checks_are_promoted_to_required_without_activation(self):
        inherited_optional = {item.control: item.availability
                              for item in self.enhanced.optional_checks}
        required_maximum = {item.control: item.availability
                            for item in self.maximum.required_checks}
        for check, availability in inherited_optional.items():
            with self.subTest(check=check):
                self.assertIn(check, required_maximum)
                self.assertIs(required_maximum[check], availability)
                self.assertNotIn(check, {r.control for r in self.maximum.optional_checks})
        self.assertEqual(set(OPTIONAL_CHECKS_BY_PROFILE[ProtectionProfileID.MAXIMUM]), set())
        self.assertEqual(set(required_maximum), set(
            REQUIRED_CHECKS_BY_PROFILE[ProtectionProfileID.ENHANCED] |
            OPTIONAL_CHECKS_BY_PROFILE[ProtectionProfileID.ENHANCED]
        ))
        self.assertEqual(set(required_maximum) - set(BASELINE_CONTROLS),
                         {PolicyControl.PDF_STRUCTURE_VALIDATION,
                          PolicyControl.ISOLATED_BEHAVIOR_ANALYSIS})
        for item in self.maximum.required_checks:
            if item.control not in BASELINE_CONTROLS:
                self.assertIs(item.availability, ControlAvailability.PLANNED)

    def test_maximum_requirements_derive_from_enhanced_policy_in_stable_order(self):
        expected = (self.enhanced.requirements + self.enhanced.optional_checks)
        self.assertEqual(_inherit_enhanced_requirements(self.enhanced), expected)
        self.assertEqual(self.maximum.requirements, expected)
        self.assertEqual(self.maximum.requirements[:len(self.enhanced.requirements)],
                         self.enhanced.requirements)
        self.assertFalse(self.maximum.optional_checks)

    def test_missing_or_downgraded_inherited_checks_are_rejected(self):
        requirements = self.maximum.requirements
        for index in range(len(requirements)):
            with self.subTest(omitted=requirements[index].control), self.assertRaises(ValueError):
                StructuredProtectionPolicy(
                    profile_id=ProtectionProfileID.MAXIMUM,
                    requirements=requirements[:index] + requirements[index + 1:],
                )
        for index, item in enumerate(requirements):
            if item.availability is ControlAvailability.CURRENT:
                altered = PolicyRequirement(item.control, ControlAvailability.PLANNED)
                with self.subTest(downgraded=item.control), self.assertRaises(ValueError):
                    StructuredProtectionPolicy(
                        profile_id=ProtectionProfileID.MAXIMUM,
                        requirements=requirements[:index] + (altered,) + requirements[index + 1:],
                    )
        with self.assertRaises(TypeError):
            _inherit_enhanced_requirements(PROTECTION_POLICIES[ProtectionProfileID.STANDARD])
        with self.assertRaises(TypeError):
            _inherit_enhanced_requirements(None)

    def test_resource_and_time_budgets_include_every_inherited_control(self):
        inherited = {item.control for item in self.enhanced.requirements}
        budget = resource_budgets_for_profile(ProtectionProfileID.MAXIMUM)
        time_limits = stage_limits_for_profile(ProtectionProfileID.MAXIMUM)
        self.assertEqual(tuple(x.control for x in budget),
                         tuple(r.control for r in self.maximum.requirements))
        self.assertEqual(tuple(x.control for x in time_limits.stages),
                         tuple(r.control for r in self.maximum.requirements))
        self.assertTrue(inherited <= {x.control for x in budget})
        self.assertTrue(inherited <= {x.control for x in time_limits.stages})
        self.assertTrue(all(x.maximum_seconds > 0 for x in time_limits.stages))

    def test_maximum_remains_inactive_and_never_authorizes_scanning(self):
        for policy in (self.enhanced, self.maximum):
            self.assertFalse(policy.selectable)
            document = json.loads(json.dumps(policy.as_document()))
            self.assertFalse(document["selectable"])
            self.assertEqual(document["failure_disposition"], "deny")
            self.assertTrue(document["requirements"])
        for saved in ("maximum", "enhanced", "standard"):
            with self.subTest(saved=saved), self.assertRaises(UnsupportedEffectivePolicy):
                resolve_effective_policy({SELECTED_PROFILE_KEY: saved})
        source = (ROOT / "scan-and-open.py").read_text(encoding="utf-8")
        self.assertNotIn("protection_policy_definitions", source)
        self.assertIn("if not cached_clean(cache_id):", source)
        self.assertFalse(PROTECTION_POLICIES[ProtectionProfileID.MAXIMUM].selectable)

    def test_inherited_contract_and_registry_are_immutable(self):
        with self.assertRaises(TypeError):
            REQUIRED_CHECKS_BY_PROFILE[ProtectionProfileID.MAXIMUM] = frozenset()
        with self.assertRaises(FrozenInstanceError):
            self.maximum.requirements = ()
        with self.assertRaises(FrozenInstanceError):
            self.enhanced.requirements[0].availability = ControlAvailability.PLANNED
        document = self.maximum.as_document()
        document["requirements"].clear()
        self.assertTrue(self.maximum.requirements)

    def test_ci_runs_both_preexisting_and_inheritance_regressions(self):
        ci = (ROOT / ".github/workflows/ci.yml").read_text(encoding="utf-8")
        self.assertIn("python3 test-required-optional-profile-checks.py -v", ci)
        self.assertIn("python3 test-structured-protection-policy.py -v", ci)
        self.assertIn("python3 test-maximum-inherits-enhanced.py -v", ci)
        self.assertIn("  macos-build:", ci)


if __name__ == "__main__":
    unittest.main()
