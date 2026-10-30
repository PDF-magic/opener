#!/usr/bin/env python3
"""Resource budget contract for policy stages, separate from elapsed-time caps."""

from dataclasses import FrozenInstanceError, replace
import json
from pathlib import Path
import unittest

from protection_profiles import ProtectionProfileID
from protection_policy_definitions import (
    ControlAvailability,
    PolicyControl,
    PROTECTION_POLICIES,
)
from protection_stage_resource_budgets import (
    PROTECTION_STAGE_RESOURCES,
    RESOURCE_BUDGET_SCHEMA_VERSION,
    ProtectionStageResources,
    ResourceCeiling,
    ResourceEnforcement,
    resource_budget_for_stage,
    resource_budgets_for_profile,
)


ROOT = Path(__file__).resolve().parent


class ProtectionStageBudgetTests(unittest.TestCase):
    def test_all_six_policy_controls_have_immutable_machine_readable_budgets(self):
        self.assertEqual(RESOURCE_BUDGET_SCHEMA_VERSION, 1)
        self.assertEqual(set(PROTECTION_STAGE_RESOURCES), set(PolicyControl))
        for control in PolicyControl:
            with self.subTest(stage=control.value):
                stage = resource_budget_for_stage(control)
                self.assertIs(stage.control, control)
                document = json.loads(json.dumps(stage.as_document()))
                self.assertEqual(document["schema_version"], 1)
                self.assertEqual(document["control"], control.value)
                self.assertEqual(set(document), {
                    "schema_version", "control", "availability", "cpu_seconds",
                    "memory_mib", "temporary_disk_mib", "concurrent_requests",
                })
                for dimension in ("cpu_seconds", "memory_mib",
                                  "temporary_disk_mib", "concurrent_requests"):
                    self.assertEqual(set(document[dimension]), {"maximum", "enforcement"})
                self.assertEqual(document["availability"], stage.availability.value)

    def test_profile_stage_coverage_matches_required_protection_policy(self):
        for profile_id in ProtectionProfileID:
            with self.subTest(profile=profile_id.value):
                stages = resource_budgets_for_profile(profile_id)
                expected = PROTECTION_POLICIES[profile_id].requirements
                self.assertEqual(
                    tuple((s.control, s.availability) for s in stages),
                    tuple((e.control, e.availability) for e in expected),
                )
                self.assertEqual(len(stages), len(set(s.control for s in stages)))
        for control in (PolicyControl.PDF_STRUCTURE_VALIDATION,
                        PolicyControl.ISOLATED_BEHAVIOR_ANALYSIS):
            self.assertIs(resource_budget_for_stage(control).availability,
                          ControlAvailability.PLANNED)

    def test_only_actual_scanner_concurrency_is_marked_current(self):
        scanner = resource_budget_for_stage(PolicyControl.CLAMAV_SCAN_GATE)
        self.assertEqual(scanner.concurrent_requests,
                         ResourceCeiling(2, ResourceEnforcement.CURRENT))
        for dimension in (scanner.cpu_seconds, scanner.memory_mib,
                          scanner.temporary_disk_mib):
            self.assertIs(dimension.enforcement, ResourceEnforcement.NOT_CONFIGURED)
            self.assertIsNone(dimension.maximum)
        for control, budget in PROTECTION_STAGE_RESOURCES.items():
            with self.subTest(stage=control.value):
                for dimension in (budget.cpu_seconds, budget.memory_mib,
                                  budget.temporary_disk_mib, budget.concurrent_requests):
                    if dimension.enforcement is ResourceEnforcement.CURRENT:
                        self.assertIs(control, PolicyControl.CLAMAV_SCAN_GATE)
                        self.assertIs(dimension, scanner.concurrent_requests)
        source = (ROOT / "scan-and-open.py").read_text(encoding="utf-8")
        self.assertIn("MAX_CONCURRENT_SCANS = 2", source)
        self.assertIn("for index in range(MAX_CONCURRENT_SCANS):", source)
        self.assertIn("PDF_SCAN_TIMEOUT = 30 * 60", source)
        # Preserve the default 30-minute scan ceiling while newer Built-in
        # policy snapshots may only tighten the active request's timeout.
        self.assertIn("pdf_timeout_seconds: int = PDF_SCAN_TIMEOUT", source)
        self.assertIn("other_timeout_seconds: int = 180", source)
        self.assertIn("timeout=(policy_snapshot.pdf_timeout_seconds if is_pdf", source)
        self.assertIn("else policy_snapshot.other_timeout_seconds)", source)

    def test_future_limits_are_positive_and_explicitly_not_enforced(self):
        for control, budget in PROTECTION_STAGE_RESOURCES.items():
            with self.subTest(stage=control.value):
                if control is PolicyControl.CLAMAV_SCAN_GATE:
                    continue
                self.assertIs(budget.cpu_seconds.enforcement, ResourceEnforcement.PLANNED)
                self.assertIs(budget.memory_mib.enforcement, ResourceEnforcement.PLANNED)
                self.assertGreater(budget.cpu_seconds.maximum, 0)
                self.assertGreater(budget.memory_mib.maximum, 0)
                self.assertIsNot(budget.concurrent_requests.enforcement,
                                 ResourceEnforcement.CURRENT)

    def test_invalid_limits_and_false_enforcement_are_rejected(self):
        for maximum in (None, 0, -1, True, False, "64", 4.5, float("inf")):
            with self.subTest(maximum=maximum), self.assertRaises(ValueError):
                ResourceCeiling(maximum, ResourceEnforcement.PLANNED)
        for status in (ResourceEnforcement.NOT_APPLICABLE,
                       ResourceEnforcement.NOT_CONFIGURED):
            with self.assertRaises(ValueError):
                ResourceCeiling(2, status)
        with self.assertRaises(TypeError):
            ResourceCeiling(64, "current")
        with self.assertRaises(TypeError):
            resource_budget_for_stage("clamav_scan_gate")
        with self.assertRaises(TypeError):
            resource_budgets_for_profile("standard")
        baseline = resource_budget_for_stage(PolicyControl.SIGNATURE_FRESHNESS)
        with self.assertRaises(ValueError):
            replace(baseline, cpu_seconds=ResourceCeiling(5, ResourceEnforcement.CURRENT))
        scanner = resource_budget_for_stage(PolicyControl.CLAMAV_SCAN_GATE)
        with self.assertRaises(ValueError):
            replace(scanner, concurrent_requests=ResourceCeiling(3, ResourceEnforcement.CURRENT))
        with self.assertRaises(ValueError):
            replace(scanner, memory_mib=ResourceCeiling(512, ResourceEnforcement.CURRENT))
        with self.assertRaises(ValueError):
            replace(baseline, availability=ControlAvailability.PLANNED)
        with self.assertRaises(TypeError):
            replace(baseline, control="signature_freshness")
        with self.assertRaises(TypeError):
            replace(baseline, memory_mib=512)
        with self.assertRaises(FrozenInstanceError):
            baseline.cpu_seconds.maximum = 1
        with self.assertRaises(FrozenInstanceError):
            scanner.availability = ControlAvailability.PLANNED
        with self.assertRaises(TypeError):
            PROTECTION_STAGE_RESOURCES[PolicyControl.CLAMAV_SCAN_GATE] = baseline

    def test_documents_are_detached_and_no_active_gate_or_preferences_change(self):
        original = resource_budget_for_stage(PolicyControl.FILE_INTEGRITY)
        document = original.as_document()
        document["memory_mib"]["maximum"] = 1
        self.assertEqual(original.memory_mib.maximum, 256)
        src = (ROOT / "protection_stage_resource_budgets.py").read_text(encoding="utf-8")
        gate = (ROOT / "scan-and-open.py").read_text(encoding="utf-8")
        self.assertNotIn("protection_stage_resource_budgets", gate)
        self.assertIn("if not cached_clean(cache_id):", gate)
        self.assertIn("'--alert-encrypted=yes'", gate)
        for forbidden in ("UserDefaults", "subprocess.run", "scan_and_open(", "os.environ",
                          "write_text(", "open(", "remove_quarantine(", "def apply_policy"):
            self.assertNotIn(forbidden, src)

    def test_budget_contract_runs_in_linux_ci(self):
        ci = (ROOT / ".github/workflows/ci.yml").read_text(encoding="utf-8")
        self.assertIn("python3 scripts/run-test.py tests/protection/stage-resource-budgets.py -v", ci)


if __name__ == "__main__":
    unittest.main()
