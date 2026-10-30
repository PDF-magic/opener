#!/usr/bin/env python3
"""Regression tests for combined ClamAV and structural evidence."""

import json
from pathlib import Path
import unittest

from combined_scan_results import (
    MAX_CLAMAV_DETECTION_NAMES,
    CombinedScanReport,
    combine_scan_results,
)
from enhanced_analysis_findings import (
    AnalysisFinding,
    AnalysisStage,
    FindingCode,
    FindingSeverity,
    StageAnalysis,
    StageOutcome,
    StructuredAnalysisFindings,
)
from scan_results import ScanResult, ScanResultStatus


ROOT = Path(__file__).resolve().parents[2]


def report_for(*findings):
    return StructuredAnalysisFindings(
        expected_stages=(AnalysisStage.pdfStructure,),
        stages=(StageAnalysis(
            AnalysisStage.pdfStructure,
            StageOutcome.completed,
            tuple(findings),
        ),),
    )


class CombinedScanResultsTests(unittest.TestCase):
    def test_clean_evidence_is_nonblocking_but_never_authorizes_opening(self):
        report = combine_scan_results(
            ScanResultStatus.clean, ScanResult(), report_for())
        payload = report.to_dict()

        self.assertIsInstance(report, CombinedScanReport)
        self.assertFalse(report.requires_block)
        self.assertFalse(report.authorizes_open)
        self.assertFalse(payload["requiresBlock"])
        self.assertFalse(payload["authorizesOpen"])
        self.assertEqual(payload["scan"]["status"], "clean")
        self.assertEqual(payload["clamav"]["effectivePolicyId"], "built-in")
        self.assertEqual(payload["clamav"]["detectionNames"], [])
        self.assertEqual(payload["structuralFindings"]["schemaVersion"], 2)
        self.assertFalse(payload["structuralFindings"]["authorizesOpen"])

    def test_clamav_detection_blocks_even_when_structure_has_no_findings(self):
        clamav = ScanResult.from_clamav_output(
            "/private/user/document.pdf: Eicar-Test-Signature FOUND")
        report = combine_scan_results(
            ScanResultStatus.malwareDetected, clamav, report_for())
        payload = report.to_dict()

        self.assertTrue(report.requires_block)
        self.assertFalse(report.authorizes_open)
        self.assertEqual(payload["clamav"]["detectionNames"],
                         ["Eicar-Test-Signature"])
        self.assertTrue(payload["requiresBlock"])
        self.assertNotIn("/private/user/document.pdf",
                         json.dumps(payload))

    def test_critical_structural_finding_blocks_a_clean_clamav_result(self):
        structural = report_for(AnalysisFinding(
            FindingCode.activeContent, FindingSeverity.critical,
            object_number=12, page_number=2))
        report = combine_scan_results(
            ScanResultStatus.clean, ScanResult(), structural)
        payload = report.to_dict()
        finding = payload["structuralFindings"]["stageResults"][0]["findings"][0]

        self.assertTrue(report.requires_block)
        self.assertTrue(payload["requiresBlock"])
        self.assertEqual(finding["code"], "activeContent")
        self.assertEqual(finding["result"]["outcome"], "blocking")
        self.assertEqual(finding["result"]["malwareAssessment"], "notConfirmed")

    def test_missing_structural_stage_blocks_a_clean_clamav_result(self):
        structural = StructuredAnalysisFindings(
            expected_stages=(
                AnalysisStage.pdfStructure,
                AnalysisStage.objectRelationships,
            ),
            stages=(StageAnalysis(
                AnalysisStage.pdfStructure, StageOutcome.completed),),
        )
        report = combine_scan_results(
            ScanResultStatus.clean, ScanResult(), structural)
        payload = report.to_dict()

        self.assertTrue(report.requires_block)
        self.assertTrue(payload["requiresBlock"])
        self.assertEqual(
            [stage["outcome"] for stage in
             payload["structuralFindings"]["stageResults"]],
            ["completed", "notRun"],
        )

    def test_every_nonclean_scan_status_requires_blocking(self):
        structural = report_for()
        for status in ScanResultStatus:
            if status is ScanResultStatus.clean:
                continue
            with self.subTest(status=status.value):
                report = combine_scan_results(status, ScanResult(), structural)
                self.assertTrue(report.requires_block)
                self.assertTrue(report.to_dict()["requiresBlock"])
                self.assertFalse(report.authorizes_open)

    def test_malware_status_blocks_even_without_a_parsed_signature_name(self):
        report = combine_scan_results(
            ScanResultStatus.malwareDetected, ScanResult(), report_for())
        self.assertTrue(report.requires_block)
        self.assertEqual(report.to_dict()["clamav"]["detectionNames"], [])

    def test_both_sources_keep_their_evidence_and_remain_separate(self):
        structural = report_for(
            AnalysisFinding(FindingCode.suspiciousUrl,
                            FindingSeverity.suspicious, object_number=8),
            AnalysisFinding(FindingCode.incrementalRevision,
                            FindingSeverity.informational, object_number=9),
        )
        clamav = ScanResult.from_clamav_output(
            "private: Eicar-Test-Signature FOUND\n"
            "private: Win.Trojan.Agent FOUND\n")
        report = combine_scan_results(
            ScanResultStatus.malwareDetected, clamav, structural)
        payload = json.loads(json.dumps(report.to_dict()))
        findings = payload["structuralFindings"]["stageResults"][0]["findings"]

        self.assertEqual(payload["clamav"]["detectionNames"],
                         ["Eicar-Test-Signature", "Win.Trojan.Agent"])
        self.assertEqual([finding["code"] for finding in findings],
                         ["suspiciousUrl", "incrementalRevision"])
        self.assertEqual([finding["result"]["outcome"] for finding in findings],
                         ["reviewRequired", "recorded"])
        self.assertTrue(payload["requiresBlock"])
        self.assertFalse(payload["authorizesOpen"])
        self.assertNotIn("private", json.dumps(payload))

        payload["clamav"]["detectionNames"].clear()
        payload["structuralFindings"]["stageResults"][0]["findings"].clear()
        rebuilt = report.to_dict()
        self.assertEqual(rebuilt["clamav"]["detectionNames"],
                         ["Eicar-Test-Signature", "Win.Trojan.Agent"])
        self.assertEqual(len(rebuilt["structuralFindings"]["stageResults"][0]["findings"]), 2)

    def test_untrusted_or_inconsistent_inputs_are_rejected(self):
        structural = report_for()
        with self.assertRaises(TypeError):
            combine_scan_results("clean", ScanResult(), structural)
        with self.assertRaises(TypeError):
            combine_scan_results(ScanResultStatus.clean, object(), structural)
        with self.assertRaises(TypeError):
            combine_scan_results(ScanResultStatus.clean, ScanResult(), {})
        with self.assertRaises(ValueError):
            combine_scan_results(
                ScanResultStatus.clean, ScanResult(("Eicar-Test-Signature",)), structural)
        with self.assertRaises(ValueError):
            combine_scan_results(
                ScanResultStatus.malwareDetected, ScanResult(("/private/path",)), structural)
        with self.assertRaises(ValueError):
            combine_scan_results(
                ScanResultStatus.malwareDetected,
                ScanResult(("Eicar-Test-Signature", "Eicar-Test-Signature")),
                structural)

    def test_detection_names_are_bounded(self):
        names = tuple(f"Signature-{index}" for index in range(MAX_CLAMAV_DETECTION_NAMES + 1))
        with self.assertRaises(ValueError):
            combine_scan_results(
                ScanResultStatus.malwareDetected, ScanResult(names), report_for())

    def test_active_scan_gate_and_planned_profile_remain_unchanged(self):
        scanner = (ROOT / "scan-and-open.py").read_text(encoding="utf-8")
        self.assertNotIn("combined_scan_results", scanner)
        self.assertIn("decision = decide_opening(detection)", scanner)
        self.assertIn("if not cached_clean(cache_id):", scanner)

        from protection_policy_definitions import PROTECTION_POLICIES, ProtectionProfileID
        self.assertFalse(PROTECTION_POLICIES[ProtectionProfileID.ENHANCED].selectable)


if __name__ == "__main__":
    unittest.main()
