#!/usr/bin/env python3
"""Schema-level tests for planned structured protection policies (opener-0250)."""

from dataclasses import FrozenInstanceError
import json
from pathlib import Path
import unittest

from protection_profiles import BASELINE_SAFETY_CHECKS, PROTECTION_PROFILES, ProtectionProfileID
from protection_policy_definitions import (
    BASELINE_CONTROLS,
    POLICY_SCHEMA_VERSION,
    PROTECTION_POLICIES,
    ControlAvailability,
    FailureDisposition,
    PolicyControl,
    PolicyRequirement,
    StructuredProtectionPolicy,
    protection_policy_definition,
)

ROOT = Path(__file__).resolve().parents[2]


class StructuredProtectionPolicyTests(unittest.TestCase):
    def test_every_profile_has_versioned_structured_machine_readable_policy(self):
        self.assertEqual(POLICY_SCHEMA_VERSION, 1)
        self.assertEqual(set(PROTECTION_POLICIES), set(PROTECTION_PROFILES))
        for identifier in ProtectionProfileID:
            with self.subTest(profile=identifier.value):
                policy = protection_policy_definition(identifier)
                definition = PROTECTION_PROFILES[identifier]
                self.assertEqual(policy.profile_id, identifier)
                self.assertEqual(policy.schema_version, 1)
                self.assertIs(policy.failure_disposition, FailureDisposition.DENY)
                self.assertFalse(policy.selectable)
                self.assertFalse(definition.selectable)
                document = json.loads(json.dumps(policy.as_document()))
                self.assertEqual(document["profile_id"], identifier.value)
                self.assertEqual(document["schema_version"], 1)
                self.assertEqual(document["failure_disposition"], "deny")
                self.assertFalse(document["selectable"])
                self.assertTrue(document["requirements"])

    def test_mandatory_scan_gates_are_current_for_every_profile(self):
        self.assertEqual(frozenset(x.value for x in BASELINE_CONTROLS),
                         BASELINE_SAFETY_CHECKS)
        for policy in PROTECTION_POLICIES.values():
            with self.subTest(profile=policy.profile_id.value):
                current = {r.control.value for r in policy.requirements
                           if r.availability is ControlAvailability.CURRENT}
                self.assertEqual(current, BASELINE_SAFETY_CHECKS)
                self.assertEqual(len(current), len(BASELINE_CONTROLS))
                self.assertEqual(len(policy.requirements),
                                 len({r.control for r in policy.requirements}))

    def test_enhanced_and_maximum_requirements_are_cumulative_but_not_active(self):
        standard = PROTECTION_POLICIES[ProtectionProfileID.STANDARD]
        enhanced = PROTECTION_POLICIES[ProtectionProfileID.ENHANCED]
        maximum = PROTECTION_POLICIES[ProtectionProfileID.MAXIMUM]
        req = lambda policy: {r.control for r in policy.requirements}
        self.assertLess(len(req(standard)), len(req(enhanced)))
        self.assertLess(len(req(enhanced)), len(req(maximum)))
        self.assertLess(req(standard), req(enhanced))
        self.assertLess(req(enhanced), req(maximum))
        self.assertEqual(req(enhanced) - req(standard),
                         {PolicyControl.PDF_STRUCTURE_VALIDATION})
        self.assertEqual(req(maximum) - req(enhanced),
                         {PolicyControl.ISOLATED_BEHAVIOR_ANALYSIS})
        for policy in (enhanced, maximum):
            for requirement in policy.requirements:
                if requirement.control not in BASELINE_CONTROLS:
                    self.assertIs(requirement.availability, ControlAvailability.PLANNED)

    def test_policy_registry_is_immutable_and_invalid_definitions_fail_closed(self):
        standard = protection_policy_definition(ProtectionProfileID.STANDARD)
        with self.assertRaises(TypeError):
            PROTECTION_POLICIES[ProtectionProfileID.STANDARD] = standard
        with self.assertRaises(FrozenInstanceError):
            standard.selectable = True
        with self.assertRaises(FrozenInstanceError):
            standard.requirements[0].availability = ControlAvailability.PLANNED
        for invalid in ("standard", "other", True, 1, None):
            with self.subTest(value=invalid), self.assertRaises(TypeError):
                protection_policy_definition(invalid)
        for changes in (
            {"selectable": True},
            {"failure_disposition": "open"},
            {"schema_version": 999},
            {"requirements": ()},
            {"requirements": standard.requirements + standard.requirements[:1]},
            {"requirements": list(standard.requirements)},
            {"requirements": tuple(
                PolicyRequirement(r.control, ControlAvailability.PLANNED)
                for r in standard.requirements
            )},
        ):
            with self.subTest(changes=changes), self.assertRaises((ValueError, TypeError)):
                StructuredProtectionPolicy(
                    profile_id=ProtectionProfileID.STANDARD,
                    requirements=changes.get("requirements", standard.requirements),
                    selectable=changes.get("selectable", False),
                    failure_disposition=changes.get("failure_disposition", FailureDisposition.DENY),
                    schema_version=changes.get("schema_version", 1),
                )

    def test_document_is_detached_and_no_scanner_or_settings_are_modified(self):
        standard = protection_policy_definition(ProtectionProfileID.STANDARD)
        document = standard.as_document()
        document["requirements"].clear()
        self.assertEqual(len(standard.requirements), len(BASELINE_CONTROLS))
        source = (ROOT / "protection_policy_definitions.py").read_text(encoding="utf-8")
        scanner = (ROOT / "scan-and-open.py").read_text(encoding="utf-8")
        self.assertNotIn("protection_policy_definitions", scanner)
        for forbidden in ("UserDefaults", "subprocess.run", "scan_and_open(", "def apply_policy",
                          "def select_profile", "os.environ", "write_text(", "open("):
            self.assertNotIn(forbidden, source)
        self.assertIn("if not cached_clean(cache_id):", scanner)
        view = (ROOT / "scan-progress-view.swift").read_text(encoding="utf-8")
        self.assertIn('static let name = "Built-in"', view)

    def test_required_ci_step(self):
        workflow = (ROOT / ".github/workflows/ci.yml").read_text(encoding="utf-8")
        self.assertIn("python3 tests/general/structured-protection-policy.py -v", workflow)


if __name__ == "__main__":
    unittest.main()
