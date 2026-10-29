#!/usr/bin/env python3
"""Regressions for opener-0297's standalone Enhanced findings contract."""

from dataclasses import FrozenInstanceError
import json
import unittest

from enhanced_analysis_findings import (
    AnalysisFinding, AnalysisStage, FindingCode, FindingSeverity,
    MAX_FINDINGS_PER_STAGE, StageAnalysis, StageOutcome,
    StructuredAnalysisFindings,
)


class StructuredAnalysisFindingsTests(unittest.TestCase):
    def test_records_machine_readable_findings_in_deterministic_stage_order(self):
        suspicious = AnalysisFinding(FindingCode.suspiciousUrl,
                                     FindingSeverity.suspicious,
                                     object_number=42, page_number=2)
        info = AnalysisFinding(FindingCode.incrementalRevision,
                               FindingSeverity.informational)
        report = StructuredAnalysisFindings(
            expected_stages=(AnalysisStage.embeddedUrls, AnalysisStage.incrementalRevisions),
            stages=(
                StageAnalysis(AnalysisStage.incrementalRevisions, StageOutcome.completed, (info,)),
                StageAnalysis(AnalysisStage.embeddedUrls, StageOutcome.completed, (suspicious,)),
            ),
        )
        payload = json.loads(json.dumps(report.to_dict()))
        self.assertEqual(payload, {
            "schemaVersion": 1,
            "authorizesOpen": False,
            "requiresBlock": True,
            "stageResults": [
                {"stage": "embeddedUrls", "outcome": "completed", "findings": [
                    {"code": "suspiciousUrl",
                     "findingId": "finding-v1:suspiciousUrl:object=42:page=2",
                     "severity": "suspicious", "objectNumber": 42, "pageNumber": 2},
                ]},
                {"stage": "incrementalRevisions", "outcome": "completed", "findings": [
                    {"code": "incrementalRevision",
                     "findingId": "finding-v1:incrementalRevision:object=none:page=none",
                     "severity": "informational", "objectNumber": None, "pageNumber": None},
                ]},
            ],
        })
        self.assertEqual(report.incomplete_stages, ())
        payload["stageResults"][0]["findings"].clear()
        self.assertEqual(len(report.to_dict()["stageResults"][0]["findings"]), 1)

    def test_finding_identifier_is_stable_and_scoped_to_code_and_location(self):
        first = AnalysisFinding(FindingCode.suspiciousUrl, FindingSeverity.suspicious,
                                object_number=42, page_number=2)
        changed_severity = AnalysisFinding(FindingCode.suspiciousUrl, FindingSeverity.critical,
                                           object_number=42, page_number=2)
        self.assertEqual(first.finding_id,
                         "finding-v1:suspiciousUrl:object=42:page=2")
        self.assertEqual(first.finding_id, changed_severity.finding_id)
        self.assertEqual(first.to_dict()["findingId"], first.finding_id)
        self.assertNotEqual(first.finding_id, AnalysisFinding(
            FindingCode.activeContent, FindingSeverity.suspicious,
            object_number=42, page_number=2).finding_id)
        self.assertNotEqual(first.finding_id, AnalysisFinding(
            FindingCode.suspiciousUrl, FindingSeverity.suspicious,
            object_number=43, page_number=2).finding_id)
        self.assertNotEqual(first.finding_id, AnalysisFinding(
            FindingCode.suspiciousUrl, FindingSeverity.suspicious,
            object_number=42, page_number=3).finding_id)
        no_location = AnalysisFinding(FindingCode.incrementalRevision,
                                      FindingSeverity.informational)
        self.assertEqual(no_location.finding_id,
                         "finding-v1:incrementalRevision:object=none:page=none")

    def test_missing_or_partial_stage_is_reported_and_blocks(self):
        report = StructuredAnalysisFindings(
            expected_stages=(AnalysisStage.pdfStructure, AnalysisStage.embeddedFiles,
                             AnalysisStage.javascriptActions),
            stages=(
                StageAnalysis(AnalysisStage.pdfStructure, StageOutcome.completed),
                StageAnalysis(AnalysisStage.embeddedFiles, StageOutcome.incomplete,
                              (AnalysisFinding(FindingCode.inspectionFailure,
                                               FindingSeverity.informational),)),
            ),
        )
        self.assertEqual(report.incomplete_stages,
                         (AnalysisStage.embeddedFiles, AnalysisStage.javascriptActions))
        self.assertTrue(report.requires_block)
        self.assertEqual(report.to_dict()["stageResults"][-1],
                         {"stage": "javascriptActions", "outcome": "notRun", "findings": []})
        self.assertEqual(report.to_dict()["stageResults"][1]["outcome"], "incomplete")

    def test_even_empty_finished_report_is_not_a_clean_scan_verdict(self):
        report = StructuredAnalysisFindings(
            (AnalysisStage.pdfStructure,),
            (StageAnalysis(AnalysisStage.pdfStructure, StageOutcome.completed),),
        )
        self.assertFalse(report.requires_block)
        self.assertFalse(report.to_dict()["authorizesOpen"])
        self.assertNotIn("clean", report.to_dict())
        self.assertNotIn("permits_open", vars(report))

    def test_untrusted_values_are_rejected_not_echoed(self):
        for code in ("suspiciousUrl", "/tmp/secret.pdf", "a\nprivate"):
            with self.subTest(code=code), self.assertRaises(TypeError):
                AnalysisFinding(code, FindingSeverity.critical)
        with self.assertRaises(TypeError):
            AnalysisFinding(FindingCode.suspiciousUrl, "suspicious")
        with self.assertRaises(TypeError):
            StageAnalysis("pdfStructure", StageOutcome.completed)
        with self.assertRaises(TypeError):
            StageAnalysis(AnalysisStage.pdfStructure, "completed")
        for number in (True, 0, -1, 2**31, "5", 2.4):
            with self.subTest(number=number), self.assertRaises(ValueError):
                AnalysisFinding(FindingCode.malformedStructure,
                                FindingSeverity.critical, object_number=number)
        with self.assertRaises(ValueError):
            AnalysisFinding(FindingCode.malformedStructure,
                            FindingSeverity.critical, page_number=1_000_001)

    def test_duplicate_unknown_missing_expectation_and_mutable_inputs_fail_closed(self):
        stage = StageAnalysis(AnalysisStage.pdfStructure, StageOutcome.completed)
        invalid_reports = (
            ((), ()),
            ((AnalysisStage.pdfStructure, AnalysisStage.pdfStructure), (stage,)),
            (("pdfStructure",), (stage,)),
            ((AnalysisStage.pdfStructure,), [stage]),
            ((AnalysisStage.pdfStructure,), (stage, stage)),
            ((AnalysisStage.embeddedFiles,), (stage,)),
            ((AnalysisStage.pdfStructure,), ("completed",)),
        )
        for expected, results in invalid_reports:
            with self.subTest(expected=expected, results=results), self.assertRaises(ValueError):
                StructuredAnalysisFindings(expected, results)
        with self.assertRaises(ValueError):
            StageAnalysis(AnalysisStage.pdfStructure, StageOutcome.completed, [])
        with self.assertRaises(ValueError):
            StageAnalysis(AnalysisStage.pdfStructure, StageOutcome.completed,
                          (AnalysisFinding(FindingCode.activeContent,
                                           FindingSeverity.critical),) * (MAX_FINDINGS_PER_STAGE + 1))
        with self.assertRaises(TypeError):
            StageAnalysis(AnalysisStage.pdfStructure, StageOutcome.completed, ("secret",))

    def test_records_are_immutable_and_informational_results_still_do_not_open(self):
        finding = AnalysisFinding(FindingCode.incrementalRevision,
                                  FindingSeverity.informational)
        stage = StageAnalysis(AnalysisStage.incrementalRevisions,
                              StageOutcome.completed, (finding,))
        report = StructuredAnalysisFindings((AnalysisStage.incrementalRevisions,), (stage,))
        for entry, field in ((finding, "code"), (stage, "stage"), (report, "stages")):
            with self.subTest(field=field), self.assertRaises(FrozenInstanceError):
                setattr(entry, field, None)
        self.assertFalse(report.requires_block)
        self.assertIs(report.to_dict()["authorizesOpen"], False)


    def test_review_required_severity_is_explicit_and_blocks(self):
        finding = AnalysisFinding(
            FindingCode.incrementalRevision, FindingSeverity.reviewRequired,
            object_number=12,
        )
        report = StructuredAnalysisFindings(
            (AnalysisStage.incrementalRevisions,),
            (StageAnalysis(AnalysisStage.incrementalRevisions,
                           StageOutcome.completed, (finding,)),),
        )
        payload = report.to_dict()
        self.assertEqual(payload["stageResults"][0]["findings"][0], {
            "code": "incrementalRevision",
            "findingId": "finding-v1:incrementalRevision:object=12:page=none",
            "severity": "reviewRequired",
            "objectNumber": 12,
            "pageNumber": None,
        })
        self.assertTrue(payload["requiresBlock"])
        self.assertFalse(payload["authorizesOpen"])


if __name__ == "__main__":
    unittest.main()
