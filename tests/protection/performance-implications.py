#!/usr/bin/env python3
"""opener-0332: never display an unmeasured performance claim."""
import json
from pathlib import Path
import unittest

from enhanced_analysis_findings import AnalysisStage, StageAnalysis, StageOutcome
from enhanced_analysis_timing import AdditionalAnalysisTimer
from protection_profiles import PROTECTION_PROFILES, ProtectionProfileID
from protection_performance_evidence import (
    PerformanceSampleGroup, build_report, encode_report,
)

ROOT = Path(__file__).resolve().parents[2]


def measured_sample(duration_ns, *, complete=True, stage=AnalysisStage.pdfStructure):
    ticks = iter([1_000_000, 1_000_000 + duration_ns])
    clock = lambda: next(ticks)
    timer = AdditionalAnalysisTimer((stage,), clock=clock)
    result = StageAnalysis(stage, StageOutcome.completed if complete else StageOutcome.incomplete)
    self_result = timer.measure(stage, lambda: result)
    assert self_result is result
    return timer.snapshot()


class PerformanceImplicationsTests(unittest.TestCase):
    def test_real_monotonic_timing_samples_produce_bounded_approximation(self):
        durations = (7_000_000, 9_000_000, 10_000_000, 12_000_000, 18_000_000)
        samples = tuple(measured_sample(x) for x in durations)
        group = PerformanceSampleGroup(ProtectionProfileID.ENHANCED, samples)
        report = build_report(group, platform="macOS sample runner", workload="one page safe PDF")
        payload = json.loads(encode_report(report))
        self.assertEqual(payload["scope"], "instrumentedAdditionalStages")
        self.assertEqual(payload["measurements"], [{
            "profile": "enhanced", "sampleCount": 5,
            "medianAdditionalMilliseconds": 10.0,
            "p90AdditionalMilliseconds": 18.0,
        }])
        self.assertNotIn("authorizesOpen", payload)
        self.assertNotIn("malwareDetected", str(payload))

    def test_partial_failed_or_non_matching_runs_are_rejected(self):
        good = measured_sample(5_000_000)
        bad = measured_sample(5_000_000, complete=False)
        with self.assertRaises(ValueError):
            PerformanceSampleGroup(ProtectionProfileID.ENHANCED, (good,) * 4)
        with self.assertRaises(ValueError):
            PerformanceSampleGroup(ProtectionProfileID.ENHANCED, (good,) * 4 + (bad,))
        with self.assertRaises(ValueError):
            PerformanceSampleGroup(ProtectionProfileID.ENHANCED, (good,) * 4 + (
                measured_sample(3_000_000, stage=AnalysisStage.annotations),))
        with self.assertRaises(ValueError):
            PerformanceSampleGroup(ProtectionProfileID.STANDARD, (good,) * 5)
        with self.assertRaises(ValueError):
            PerformanceSampleGroup(ProtectionProfileID.MAXIMUM, (good,) * 102)

    def test_reports_never_fabricate_a_profile_average(self):
        report = build_report(platform="macOS sample runner", workload="one page safe PDF")
        self.assertEqual(report["measurements"], [])
        self.assertNotIn("medianAdditionalMilliseconds", str(report))
        with self.assertRaises(ValueError):
            build_report(platform="../../private", workload="one page safe PDF")
        with self.assertRaises(ValueError):
            build_report(platform="macOS sample runner", workload="/Users/name/private.pdf")

    def test_bundled_resource_is_explicitly_unmeasured_until_real_benchmarks(self):
        fixture = json.loads((ROOT / "PDFMagicOpenerApp" / "protection-performance.json").read_text())
        self.assertEqual(fixture["schemaVersion"], 1)
        self.assertEqual(fixture["scope"], "instrumentedAdditionalStages")
        self.assertEqual(fixture["measurements"], [])
        self.assertFalse(any("median" in key for key in fixture))

    def test_native_view_loads_only_valid_evidence_and_preserves_unknown_state(self):
        source = (ROOT / "PDFMagicOpenerApp" / "ProtectionSettingsView.swift").read_text()
        for term in (
            "Bundle.main.url(",
            'forResource: "protection-performance", withExtension: "json"',
            "JSONDecoder().decode(ProtectionPerformanceEvidence.self, from: contents)",
            "sampleCount >= 5", "milliseconds.isFinite", "p90.isFinite",
            'scope == "instrumentedAdditionalStages"',
            "Measured additional inspection time",
            "No representative performance measurements yet",
            "Not a measured end-to-end opening estimate",
        ):
            with self.subTest(term=term):
                self.assertIn(term, source)
        for prohibited in (
            "UserDefaults", "@AppStorage", "FileManager", "Process(",
            "NSWorkspace", "URLSession", "clamscan(", "save(",
        ):
            with self.subTest(prohibited=prohibited):
                self.assertNotIn(prohibited, source)

    def test_scanner_and_persisted_policy_still_unchanged(self):
        self.assertTrue(all(not x.selectable for x in PROTECTION_PROFILES.values()))
        engine = (ROOT / "scan-and-open.py").read_text()
        self.assertNotIn("protection_performance_evidence", engine)
        self.assertIn("if not cached_clean(cache_id):", engine)
        project = (ROOT / "PDFMagicOpener.xcodeproj" / "project.pbxproj").read_text()
        self.assertIn("protection-performance.json", project)
        ci = (ROOT / ".github/workflows/ci.yml").read_text()
        self.assertIn("python3 tests/protection/performance-implications.py -v", ci)


if __name__ == "__main__":
    unittest.main()
