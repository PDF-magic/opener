#!/usr/bin/env python3
"""Validate non-executable per-stage resource budgets for opener-0258."""

from dataclasses import FrozenInstanceError, replace
import json
from pathlib import Path
import unittest

from file_lifecycle import FileState
from protection_stage_budgets import (
    BUDGET_SCHEMA_VERSION,
    STAGE_RESOURCE_BUDGETS,
    BudgetEnforcement,
    ResourceCeiling,
    StageResourceBudget,
    stage_resource_budget,
)

ROOT = Path(__file__).resolve().parent


class StageResourceBudgetTests(unittest.TestCase):
    def test_all_lifecycle_stages_have_immutable_json_resource_budgets(self):
        self.assertEqual(BUDGET_SCHEMA_VERSION, 1)
        self.assertEqual(set(STAGE_RESOURCE_BUDGETS), set(FileState))
        for stage in FileState:
            with self.subTest(stage=stage.value):
                budget = stage_resource_budget(stage)
                self.assertIs(budget.stage, stage)
                values = json.loads(json.dumps(budget.as_document()))
                self.assertEqual(values["schema_version"], 1)
                self.assertEqual(values["stage"], stage.value)
                self.assertEqual(set(values), {
                    "schema_version", "stage", "pdf_wall_seconds",
                    "other_wall_seconds", "cpu_seconds", "memory_mib",
                    "concurrent_requests",
                })
                for key in ("pdf_wall_seconds", "other_wall_seconds", "cpu_seconds",
                            "memory_mib", "concurrent_requests"):
                    self.assertEqual(set(values[key]), {"limit", "enforcement"})

    def test_current_limits_match_the_installed_scanner_not_a_hypothetical_policy(self):
        scanning = stage_resource_budget(FileState.SCANNING)
        self.assertEqual(scanning.pdf_wall_seconds,
                         ResourceCeiling(30 * 60, BudgetEnforcement.CURRENT))
        self.assertEqual(scanning.other_wall_seconds,
                         ResourceCeiling(3 * 60, BudgetEnforcement.CURRENT))
        self.assertEqual(scanning.concurrent_requests,
                         ResourceCeiling(2, BudgetEnforcement.CURRENT))
        self.assertIs(scanning.cpu_seconds.enforcement, BudgetEnforcement.NOT_CONFIGURED)
        self.assertIs(scanning.memory_mib.enforcement, BudgetEnforcement.NOT_CONFIGURED)
        gate = (ROOT / "scan-and-open.py").read_text(encoding="utf-8")
        self.assertIn("PDF_SCAN_TIMEOUT = 30 * 60", gate)
        self.assertIn("MAX_CONCURRENT_SCANS = 2", gate)
        self.assertIn("timeout=PDF_SCAN_TIMEOUT if is_pdf else 180", gate)
        self.assertIn("'--max-scantime=0'", gate)

    def test_planned_budgets_are_explicit_but_never_misrepresented_as_enforced(self):
        for stage in (FileState.QUEUED, FileState.ANALYZING,
                      FileState.READY, FileState.OPENING):
            with self.subTest(stage=stage.value):
                budget = stage_resource_budget(stage)
                self.assertIs(budget.pdf_wall_seconds.enforcement, BudgetEnforcement.PLANNED)
                self.assertIs(budget.other_wall_seconds.enforcement, BudgetEnforcement.PLANNED)
                self.assertGreater(budget.pdf_wall_seconds.limit, 0)
                self.assertGreater(budget.other_wall_seconds.limit, 0)
                self.assertFalse(any(
                    item.enforcement is BudgetEnforcement.CURRENT
                    for item in (budget.cpu_seconds, budget.memory_mib,
                                 budget.concurrent_requests)
                ))
        queued = stage_resource_budget(FileState.QUEUED)
        self.assertIs(queued.concurrent_requests.enforcement,
                      BudgetEnforcement.NOT_CONFIGURED)
        self.assertIs(queued.cpu_seconds.enforcement, BudgetEnforcement.NOT_APPLICABLE)
        for stage in (FileState.BLOCKED, FileState.COMPLETED):
            values = stage_resource_budget(stage).as_document()
            for name in ("pdf_wall_seconds", "other_wall_seconds",
                         "cpu_seconds", "memory_mib", "concurrent_requests"):
                self.assertEqual(values[name],
                                 {"limit": None, "enforcement": "not_applicable"})

    def test_invalid_budgets_cannot_claim_current_enforcement_or_create_work(self):
        for limit in (0, -1, True, 3.5, "30", None):
            with self.subTest(limit=limit), self.assertRaises(ValueError):
                ResourceCeiling(limit, BudgetEnforcement.CURRENT)
        for status in (BudgetEnforcement.NOT_CONFIGURED, BudgetEnforcement.NOT_APPLICABLE):
            with self.subTest(status=status), self.assertRaises(ValueError):
                ResourceCeiling(1, status)
        with self.assertRaises(TypeError):
            ResourceCeiling(1, "current")
        with self.assertRaises(TypeError):
            stage_resource_budget("scanning")
        with self.assertRaises(TypeError):
            replace(stage_resource_budget(FileState.SCANNING), stage="scanning")
        with self.assertRaises(TypeError):
            replace(stage_resource_budget(FileState.SCANNING), memory_mib=512)
        with self.assertRaises(ValueError):
            replace(stage_resource_budget(FileState.COMPLETED),
                    memory_mib=ResourceCeiling(1, BudgetEnforcement.PLANNED))
        with self.assertRaises(FrozenInstanceError):
            stage_resource_budget(FileState.SCANNING).pdf_wall_seconds.limit = 0
        with self.assertRaises(FrozenInstanceError):
            stage_resource_budget(FileState.READY).stage = FileState.SCANNING
        with self.assertRaises(TypeError):
            STAGE_RESOURCE_BUDGETS[FileState.SCANNING] = stage_resource_budget(FileState.READY)

    def test_detached_contract_does_not_change_scanner_or_user_customizations(self):
        document = stage_resource_budget(FileState.SCANNING).as_document()
        document["pdf_wall_seconds"]["limit"] = 1
        self.assertEqual(stage_resource_budget(FileState.SCANNING).pdf_wall_seconds.limit, 1800)
        source = (ROOT / "protection_stage_budgets.py").read_text(encoding="utf-8")
        scanner = (ROOT / "scan-and-open.py").read_text(encoding="utf-8")
        self.assertNotIn("protection_stage_budgets", scanner)
        for forbidden in ("UserDefaults", "subprocess.run", "scan_and_open(",
                          "def apply_policy", "def select_profile", "os.environ",
                          "write_text(", "open("):
            self.assertNotIn(forbidden, source)
        self.assertIn("if not cached_clean(cache_id):", scanner)
        self.assertIn("'--alert-encrypted=yes'", scanner)

    def test_new_ci_check_is_registered(self):
        workflow = (ROOT / ".github/workflows/ci.yml").read_text(encoding="utf-8")
        self.assertIn("python3 test-protection-stage-budgets.py -v", workflow)


if __name__ == "__main__":
    unittest.main()
