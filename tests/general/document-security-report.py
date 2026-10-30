#!/usr/bin/env python3
"""Regression tests for concise, non-authorizing document-security reports."""

from pathlib import Path
import unittest

from combined_scan_results import combine_scan_results
from document_security_report import (
    DocumentSecurityReport,
    MAX_DISPLAYED_SIGNATURES,
    create_document_security_report,
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


def structural_report(
    findings=(),
    expected_stages=(AnalysisStage.pdfStructure,),
    stages=None,
):
    if stages is None:
        stages = (
            StageAnalysis(expected_stages[0], StageOutcome.completed, tuple(findings)),
        )
    return StructuredAnalysisFindings(
        expected_stages=expected_stages,
        stages=stages,
    )


def make_report(status=ScanResultStatus.clean, clamav=None, structural=None):
    return create_document_security_report(combine_scan_results(
        status,
        ScanResult() if clamav is None else clamav,
        structural_report() if structural is None else structural,
    ))


class DocumentSecurityReportTests(unittest.TestCase):
    def test_clean_evidence_is_summarized_without_claiming_the_document_is_safe(self):
        report = make_report()
        payload = report.to_dict()
        text = report.to_text()

        self.assertIsInstance(report, DocumentSecurityReport)
        self.assertFalse(report.requires_block)
        self.assertFalse(report.authorizes_open)
        self.assertFalse(payload["requiresBlock"])
        self.assertFalse(payload["authorizesOpen"])
        self.assertEqual(payload["schemaVersion"], 1)
        self.assertEqual(payload["headline"],
                         "Document security: No blocking findings reported")
        self.assertIn("ClamAV: No malware signatures detected", text)
        self.assertIn("No findings reported across 1 completed stage", text)
        self.assertIn("this is not a clean verdict", text)
        self.assertIn("Opening authorization: Not granted", text)

    def test_clamav_detection_blocks_and_report_does_not_disclose_the_file_path(self):
        clamav = ScanResult.from_clamav_output(
            "/Users/private/annual-report.pdf: Eicar-Test-Signature FOUND")
        report = make_report(ScanResultStatus.malwareDetected, clamav=clamav)
        text = report.to_text()

        self.assertTrue(report.requires_block)
        self.assertEqual(report.headline, "Document security: BLOCKED")
        self.assertIn("ClamAV: Malware detected (1 signature: Eicar-Test-Signature)", text)
        self.assertIn("Keep the document blocked", text)
        self.assertNotIn("/Users/private", text)
        self.assertNotIn("annual-report.pdf", text)

    def test_malware_status_without_a_safe_signature_name_still_blocks(self):
        report = make_report(ScanResultStatus.malwareDetected)

        self.assertTrue(report.requires_block)
        self.assertIn("signature details unavailable", report.scan_summary)
        self.assertFalse(report.authorizes_open)

    def test_critical_structural_finding_blocks_when_clamav_reports_no_signature(self):
        structural = structural_report((
            AnalysisFinding(
                FindingCode.activeContent,
                FindingSeverity.critical,
                object_number=12,
                page_number=2,
            ),
        ))
        report = make_report(structural=structural)

        self.assertTrue(report.requires_block)
        self.assertIn("ClamAV: No malware signatures detected", report.scan_summary)
        self.assertIn("1 finding (1 blocking)", report.structural_summary)
        self.assertIn("Keep the document blocked", report.next_step)
        self.assertFalse(report.authorizes_open)

    def test_structural_findings_are_summarized_by_handling_outcome(self):
        structural = structural_report((
            AnalysisFinding(
                FindingCode.suspiciousUrl,
                FindingSeverity.suspicious,
                object_number=8,
            ),
            AnalysisFinding(
                FindingCode.incrementalRevision,
                FindingSeverity.informational,
                object_number=9,
            ),
        ))
        report = make_report(structural=structural)

        self.assertTrue(report.requires_block)
        self.assertIn(
            "2 findings (1 review required, 1 informational)",
            report.structural_summary,
        )
        self.assertIn("1 stage completed", report.structural_summary)

    def test_incomplete_structural_stages_are_visible_and_fail_closed(self):
        expected = (
            AnalysisStage.pdfStructure,
            AnalysisStage.objectRelationships,
            AnalysisStage.embeddedFiles,
        )
        structural = structural_report(
            expected_stages=expected,
            stages=(
                StageAnalysis(AnalysisStage.pdfStructure, StageOutcome.completed),
                StageAnalysis(AnalysisStage.objectRelationships, StageOutcome.incomplete),
            ),
        )
        report = make_report(structural=structural)

        self.assertTrue(report.requires_block)
        self.assertIn("No findings recorded", report.structural_summary)
        self.assertIn("2 of 3 stages incomplete", report.structural_summary)
        self.assertIn("Keep the document blocked", report.next_step)

    def test_every_nonclean_scan_status_has_a_fixed_summary_and_blocks(self):
        for status in ScanResultStatus:
            if status is ScanResultStatus.clean:
                continue
            with self.subTest(status=status.value):
                report = make_report(status)
                self.assertTrue(report.requires_block)
                self.assertFalse(report.authorizes_open)
                self.assertTrue(report.scan_summary)
                self.assertFalse(report.scan_summary.endswith("None."))

    def test_signature_display_is_bounded_and_excess_names_are_counted(self):
        names = (
            "Alpha.Signature",
            "Beta.Signature",
            "Long.Signature." + "x" * 100,
            "Delta.Signature",
        )
        report = make_report(
            ScanResultStatus.malwareDetected,
            clamav=ScanResult(names),
        )

        self.assertIn("4 signatures", report.scan_summary)
        self.assertIn("+1 more", report.scan_summary)
        self.assertLessEqual(len(report.scan_summary), 250)
        self.assertNotIn("Delta.Signature", report.scan_summary)
        self.assertNotIn("x" * 100, report.scan_summary)
        self.assertEqual(MAX_DISPLAYED_SIGNATURES, 3)

    def test_report_schema_is_stable_and_never_authorizes_opening(self):
        report = make_report()
        payload = report.to_dict()

        self.assertEqual(set(payload), {
            "schemaVersion", "authorizesOpen", "requiresBlock", "headline",
            "scanSummary", "structuralSummary", "nextStep",
        })
        self.assertIs(payload["authorizesOpen"], False)
        self.assertIs(report.authorizes_open, False)

    def test_invalid_combined_evidence_is_rejected(self):
        with self.assertRaises(TypeError):
            create_document_security_report({"scan": "clean"})

    def test_existing_scanner_gate_and_user_profile_defaults_are_unchanged(self):
        scanner = (ROOT / "scan-and-open.py").read_text(encoding="utf-8")
        self.assertIn("decision = decide_opening(detection)", scanner)
        self.assertIn("if not cached_clean(cache_id):", scanner)
        self.assertNotIn("create_document_security_report", scanner)

        from protection_policy_definitions import PROTECTION_POLICIES, ProtectionProfileID
        self.assertFalse(PROTECTION_POLICIES[ProtectionProfileID.ENHANCED].selectable)


if __name__ == "__main__":
    unittest.main()
