#!/usr/bin/env python3
"""Deterministic timing and scanner-isolation regressions for opener-0304."""

from dataclasses import FrozenInstanceError
import json
from pathlib import Path
import unittest
from unittest.mock import Mock

from enhanced_analysis_findings import AnalysisStage, StageAnalysis, StageOutcome
from enhanced_analysis_timing import (
    AdditionalAnalysisTimer, AdditionalAnalysisTiming,
    AdditionalAnalysisTimingError, BLOCK_MESSAGE, MAX_ELAPSED_NS, StageTiming,
)


def ticks(*values):
    values = iter(values)
    return lambda: next(values)


class AdditionalAnalysisTimingTests(unittest.TestCase):
    def test_monotonic_extra_time_excludes_idle_gaps_and_unrun_stages(self):
        first, second, missing = (
            AnalysisStage.pdfStructure, AnalysisStage.annotations, AnalysisStage.embeddedUrls)
        timer = AdditionalAnalysisTimer(
            (first, second, missing),
            clock=ticks(1_000_000, 11_000_000, 101_000_000, 104_500_000))
        original = StageAnalysis(first, StageOutcome.completed)
        self.assertIs(timer.measure(first, lambda: original), original)
        timer.measure(second, lambda: StageAnalysis(second, StageOutcome.completed))
        result = timer.snapshot()
        self.assertEqual(result.additional_nanoseconds, 13_500_000)
        self.assertFalse(result.timing_complete)
        self.assertEqual(json.loads(json.dumps(result.to_dict())), {
            "schemaVersion": 1,
            "additionalAnalysisNanoseconds": 13_500_000,
            "timingComplete": False, "authorizesOpen": False,
            "stageTimings": [
                {"stage": "pdfStructure", "outcome": "completed",
                 "elapsedNanoseconds": 10_000_000},
                {"stage": "annotations", "outcome": "completed",
                 "elapsedNanoseconds": 3_500_000},
                {"stage": "embeddedUrls", "outcome": "notRun",
                 "elapsedNanoseconds": None},
            ],
        })

    def test_complete_measurements_never_authorize_open(self):
        stages = (AnalysisStage.pdfStructure, AnalysisStage.annotations)
        timer = AdditionalAnalysisTimer(stages, clock=ticks(10, 20, 30, 34))
        for stage in stages:
            timer.measure(stage, lambda stage=stage: StageAnalysis(stage, StageOutcome.completed))
        report = timer.snapshot()
        self.assertTrue(report.timing_complete)
        self.assertEqual(report.additional_nanoseconds, 14)
        self.assertFalse(report.authorizes_open)
        self.assertFalse(report.to_dict()["authorizesOpen"])

    def test_incomplete_result_preserves_status(self):
        stage = AnalysisStage.javascriptActions
        timer = AdditionalAnalysisTimer((stage,), clock=ticks(10, 90))
        result = StageAnalysis(stage, StageOutcome.incomplete)
        self.assertIs(timer.measure(stage, lambda: result), result)
        self.assertFalse(timer.snapshot().timing_complete)
        self.assertEqual(timer.snapshot().stages[0].outcome, StageOutcome.incomplete)

    def test_failed_stage_propagates_same_exception_and_records_no_details(self):
        stage = AnalysisStage.embeddedFiles
        timer = AdditionalAnalysisTimer((stage,), clock=ticks(100, 150))
        failure = RuntimeError("private /secret/file.pdf")
        def broken():
            raise failure
        with self.assertRaises(RuntimeError) as seen:
            timer.measure(stage, broken)
        self.assertIs(seen.exception, failure)
        report = timer.snapshot()
        self.assertFalse(report.timing_complete)
        self.assertEqual(report.stages[0].elapsed_nanoseconds, 50)
        self.assertEqual(report.stages[0].outcome, StageOutcome.incomplete)
        self.assertNotIn("private", repr(report.to_dict()))
        self.assertFalse(report.authorizes_open)

    def test_invalid_results_are_timed_as_incomplete_not_clean(self):
        stage = AnalysisStage.pdfStructure
        timer = AdditionalAnalysisTimer((stage,), clock=ticks(1, 5))
        with self.assertRaises(TypeError):
            timer.measure(stage, lambda: StageAnalysis(
                AnalysisStage.annotations, StageOutcome.completed))
        self.assertFalse(timer.snapshot().timing_complete)
        self.assertEqual(timer.snapshot().stages[0].outcome, StageOutcome.incomplete)
        other = AdditionalAnalysisTimer((stage,), clock=ticks(1, 3))
        with self.assertRaises(TypeError):
            other.measure(stage, lambda: True)
        self.assertFalse(other.snapshot().timing_complete)

    def test_repeated_unexpected_nested_and_active_inspection_rejected(self):
        first, second = AnalysisStage.pdfStructure, AnalysisStage.annotations
        timer = AdditionalAnalysisTimer((first, second), clock=ticks(10, 20))
        never = Mock()
        with self.assertRaises(ValueError):
            timer.measure(AnalysisStage.embeddedFiles, never)
        with self.assertRaises(TypeError):
            timer.measure(first, None)
        def inside():
            with self.assertRaises(AdditionalAnalysisTimingError):
                timer.snapshot()
            with self.assertRaises(ValueError):
                timer.measure(second, never)
            return StageAnalysis(first, StageOutcome.completed)
        timer.measure(first, inside)
        with self.assertRaises(ValueError):
            timer.measure(first, never)
        never.assert_not_called()

    def test_invalid_and_decreasing_clock_values_fail_closed(self):
        stage = AnalysisStage.pdfStructure
        samples = ((20, 10), (20, "bad"), (-1,), (True,), (MAX_ELAPSED_NS + 1,))
        for values in samples:
            with self.subTest(values=values):
                timer = AdditionalAnalysisTimer((stage,), clock=ticks(*values))
                with self.assertRaises(AdditionalAnalysisTimingError) as failure:
                    timer.measure(stage, lambda: StageAnalysis(stage, StageOutcome.completed))
                self.assertEqual(str(failure.exception), BLOCK_MESSAGE)
                self.assertFalse(timer.snapshot().timing_complete)
        failing = AdditionalAnalysisTimer((stage,), clock=Mock(side_effect=OSError("/secret")))
        with self.assertRaises(AdditionalAnalysisTimingError):
            failing.measure(stage, lambda: StageAnalysis(stage, StageOutcome.completed))

    def test_records_are_immutable_and_validate_untrusted_inputs(self):
        first, second = AnalysisStage.pdfStructure, AnalysisStage.annotations
        record = StageTiming(first, StageOutcome.completed, 1)
        report = AdditionalAnalysisTiming((first, second), (record,))
        with self.assertRaises(FrozenInstanceError):
            record.elapsed_nanoseconds = 3
        with self.assertRaises(FrozenInstanceError):
            report.stages = ()
        payload = report.to_dict()
        payload["stageTimings"][0]["elapsedNanoseconds"] = 8
        self.assertEqual(report.to_dict()["stageTimings"][0]["elapsedNanoseconds"], 1)
        for bad in (-1, True, 1.5, "50", None, MAX_ELAPSED_NS + 1):
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                StageTiming(first, StageOutcome.completed, bad)
        with self.assertRaises(ValueError):
            AdditionalAnalysisTiming((first, second), (record, record))
        with self.assertRaises(ValueError):
            AdditionalAnalysisTiming((first,), (StageTiming(second, StageOutcome.completed, 2),))
        with self.assertRaises(ValueError):
            AdditionalAnalysisTiming((first, second), (
                StageTiming(second, StageOutcome.completed, 2), record))
        for invalid in ((), (first, first), [first], (first, "pdfStructure")):
            with self.subTest(invalid=invalid), self.assertRaises(ValueError):
                AdditionalAnalysisTimer(invalid)
        with self.assertRaises(TypeError):
            AdditionalAnalysisTimer((first,), clock=17)

    def test_installed_scanner_and_profile_configuration_remain_unchanged(self):
        root = Path(__file__).resolve().parents[2]
        scanner = (root / "scan-and-open.py").read_text(encoding="utf-8")
        self.assertNotIn("enhanced_analysis_timing", scanner)
        self.assertIn("if not cached_clean(cache_id):", scanner)
        from protection_policy_definitions import PROTECTION_POLICIES, ProtectionProfileID
        self.assertFalse(PROTECTION_POLICIES[ProtectionProfileID.ENHANCED].selectable)


if __name__ == "__main__":
    unittest.main()
