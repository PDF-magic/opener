#!/usr/bin/env python3
"""Regression coverage for declarative per-stage time budgets (opener-0257)."""

from dataclasses import FrozenInstanceError
import ast
import json
from pathlib import Path
import unittest

from protection_profiles import ProtectionProfileID
from protection_policy_definitions import (
    ControlAvailability,
    PolicyControl,
    PROTECTION_POLICIES,
)
from protection_stage_time_limits import (
    STAGE_MAXIMUM_SECONDS,
    STAGE_TIME_LIMIT_SCHEMA_VERSION,
    PROFILE_STAGE_LIMITS,
    ProcessingStageLimit,
    ProfileStageLimits,
    stage_limits_for_profile,
)


ROOT = Path(__file__).resolve().parent


class StageLimitTests(unittest.TestCase):
    def test_every_known_stage_has_a_finite_positive_explicit_maximum(self):
        expected = {
            PolicyControl.SIGNATURE_FRESHNESS: 20,
            PolicyControl.FILE_INTEGRITY: 300,
            PolicyControl.CLAMAV_SCAN_GATE: 1800,
            PolicyControl.PDF_STRUCTURE_VALIDATION: 120,
            PolicyControl.ISOLATED_BEHAVIOR_ANALYSIS: 600,
            PolicyControl.FAIL_CLOSED_HANDOFF: 60,
        }
        self.assertEqual(dict(STAGE_MAXIMUM_SECONDS), expected)
        self.assertEqual(set(STAGE_MAXIMUM_SECONDS), set(PolicyControl))
        self.assertEqual(STAGE_TIME_LIMIT_SCHEMA_VERSION, 1)
        for stage, seconds in STAGE_MAXIMUM_SECONDS.items():
            with self.subTest(stage=stage.value):
                self.assertIs(type(seconds), int)
                self.assertGreater(seconds, 0)

    def test_every_profile_covers_required_current_and_planned_stages(self):
        self.assertEqual(set(PROFILE_STAGE_LIMITS), set(ProtectionProfileID))
        for identifier in ProtectionProfileID:
            with self.subTest(profile=identifier.value):
                result = stage_limits_for_profile(identifier)
                policy = PROTECTION_POLICIES[identifier]
                self.assertEqual(result.profile_id, identifier)
                self.assertEqual(result.schema_version, 1)
                self.assertEqual(
                    tuple((stage.control, stage.availability) for stage in result.stages),
                    tuple((req.control, req.availability) for req in policy.requirements),
                )
                self.assertEqual(len(result.stages), len({item.control for item in result.stages}))
                for stage in result.stages:
                    self.assertEqual(stage.maximum_seconds, STAGE_MAXIMUM_SECONDS[stage.control])
                    self.assertEqual(
                        stage.availability,
                        next(req.availability for req in policy.requirements
                             if req.control == stage.control),
                    )
                document = json.loads(json.dumps(result.as_document()))
                self.assertEqual(document["profile_id"], identifier.value)
                self.assertEqual(document["schema_version"], 1)
                self.assertEqual(len(document["stages"]), len(result.stages))
        for identifier in (ProtectionProfileID.ENHANCED, ProtectionProfileID.MAXIMUM):
            proposed = [
                stage for stage in PROFILE_STAGE_LIMITS[identifier].stages
                if stage.control in (
                    PolicyControl.PDF_STRUCTURE_VALIDATION,
                    PolicyControl.ISOLATED_BEHAVIOR_ANALYSIS,
                )
            ]
            self.assertTrue(proposed)
            self.assertTrue(all(stage.availability is ControlAvailability.PLANNED
                                for stage in proposed))

    def test_limits_are_immutable_and_reject_unsafe_or_incomplete_values(self):
        standard = stage_limits_for_profile(ProtectionProfileID.STANDARD)
        with self.assertRaises(TypeError):
            STAGE_MAXIMUM_SECONDS[PolicyControl.CLAMAV_SCAN_GATE] = 1
        with self.assertRaises(TypeError):
            PROFILE_STAGE_LIMITS[ProtectionProfileID.STANDARD] = standard
        with self.assertRaises(FrozenInstanceError):
            standard.stages[0].maximum_seconds = 1
        with self.assertRaises(FrozenInstanceError):
            standard.profile_id = ProtectionProfileID.MAXIMUM
        for bad in ("standard", None, True, 1):
            with self.subTest(invalid_profile=bad), self.assertRaises(TypeError):
                stage_limits_for_profile(bad)
        reference = standard.stages[0]
        for bad in (0, -10, 1.5, True, False, "60", None, float("inf"), 100000):
            with self.subTest(invalid_seconds=bad), self.assertRaises(ValueError):
                ProcessingStageLimit(reference.control, bad, reference.availability)
        with self.assertRaises(TypeError):
            ProcessingStageLimit("clamav_scan_gate", 1800, ControlAvailability.CURRENT)
        with self.assertRaises(TypeError):
            ProcessingStageLimit(reference.control, reference.maximum_seconds, "current")
        for bad_stages in (
            (),
            standard.stages[:-1],
            standard.stages + standard.stages[:1],
            list(standard.stages),
            tuple(reversed(standard.stages)),
        ):
            with self.subTest(invalid_stages=repr(bad_stages)), self.assertRaises((ValueError, TypeError)):
                ProfileStageLimits(ProtectionProfileID.STANDARD, bad_stages)
        with self.assertRaises(ValueError):
            ProfileStageLimits(ProtectionProfileID.STANDARD, standard.stages, schema_version=2)
        with self.assertRaises(ValueError):
            ProfileStageLimits(ProtectionProfileID.STANDARD, standard.stages, schema_version=True)

    def test_metadata_cannot_mutate_existing_scanner_or_preferences(self):
        standard = stage_limits_for_profile(ProtectionProfileID.STANDARD)
        description = standard.as_document()
        description["stages"][0]["maximum_seconds"] = 1
        description["stages"].clear()
        self.assertEqual(len(standard.stages), len(PROTECTION_POLICIES[ProtectionProfileID.STANDARD].requirements))
        self.assertNotEqual(standard.stages[0].maximum_seconds, 1)

        source = (ROOT / "protection_stage_time_limits.py").read_text(encoding="utf-8")
        scanner = (ROOT / "scan-and-open.py").read_text(encoding="utf-8")
        preferences = (ROOT / "PDFMagicOpenerApp" / "ScanProgressPreference.swift").read_text(encoding="utf-8")
        self.assertNotIn("protection_stage_time_limits", scanner)
        self.assertNotIn("protection_stage_time_limits", preferences)
        for forbidden in ("subprocess.", "UserDefaults", "launch_clean_file(", "remove_quarantine(",
                          "scan_and_open(", "os.environ", "write_text(", "def enforce", "def apply"):
            self.assertNotIn(forbidden, source)
        parsed = ast.parse(scanner)
        definition = next(
            node.value for node in parsed.body
            if isinstance(node, ast.Assign) and len(node.targets) == 1
            and isinstance(node.targets[0], ast.Name)
            and node.targets[0].id == "PDF_SCAN_TIMEOUT"
        )
        self.assertIsInstance(definition, ast.BinOp)
        self.assertIsInstance(definition.op, ast.Mult)
        self.assertEqual(
            ast.literal_eval(definition.left) * ast.literal_eval(definition.right),
            STAGE_MAXIMUM_SECONDS[PolicyControl.CLAMAV_SCAN_GATE],
        )
        # The installed scanner now snapshots tightened, request-scoped limits.
        # Both remain bounded by PDF_SCAN_TIMEOUT and the 180-second other-file cap.
        self.assertIn("timeout=(policy_snapshot.pdf_timeout_seconds if is_pdf", scanner)
        self.assertIn("else policy_snapshot.other_timeout_seconds", scanner)
        self.assertIn("except subprocess.TimeoutExpired:", scanner)
        self.assertIn("if not cached_clean(cache_id):", scanner)

    def test_ci_runs_stage_limit_regression(self):
        ci = (ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")
        self.assertIn("python3 test-protection-stage-time-limits.py -v", ci)


if __name__ == "__main__":
    unittest.main()
