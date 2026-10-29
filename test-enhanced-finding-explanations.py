#!/usr/bin/env python3
"""Executable regression tests for opener-0299's finding explanations."""

from dataclasses import FrozenInstanceError
import json
from pathlib import Path
import unittest

from enhanced_analysis_findings import (
    AnalysisFinding, AnalysisStage, FindingCode, FindingSeverity,
    StageAnalysis, StageOutcome, StructuredAnalysisFindings,
)
from enhanced_finding_explanations import (
    ExplainedFinding, ExplainableAnalysisFindings, FindingNextAction,
    FindingResult, explain_analysis_findings,
)


def report_for(*findings, outcome=StageOutcome.completed):
    return StructuredAnalysisFindings(
        (AnalysisStage.malformedStructures,),
        (StageAnalysis(AnalysisStage.malformedStructures, outcome, findings),),
    )


class FindingExplanationsTests(unittest.TestCase):
    def test_explains_every_known_finding_code_without_raw_pdf_strings(self):
        every_code = tuple(AnalysisFinding(code, FindingSeverity.informational)
                           for code in FindingCode)
        result = explain_analysis_findings(report_for(*every_code))
        payload = result.to_dict()
        self.assertEqual(len(payload["stageResults"][0]["findings"]), len(FindingCode))
        self.assertEqual([entry["code"] for entry in payload["stageResults"][0]["findings"]],
                         [code.value for code in FindingCode])
        for entry in payload["stageResults"][0]["findings"]:
            outcome = entry["result"]
            self.assertTrue(outcome["explanation"])
            self.assertEqual(set(outcome), {"outcome", "explanation", "nextAction"})
            self.assertNotIn("/tmp/", str(outcome))
            self.assertNotIn("http://", str(outcome))
        self.assertTrue(payload["requiresBlock"])  # failures cannot be informational bypasses
        self.assertFalse(payload["authorizesOpen"])

    def test_severities_have_deterministic_outcomes_and_actions(self):
        variants = (
            (FindingSeverity.informational, FindingResult.recorded,
             FindingNextAction.continueRequiredChecks),
            (FindingSeverity.reviewRequired, FindingResult.reviewRequired,
             FindingNextAction.requestReviewBeforeOpening),
            (FindingSeverity.suspicious, FindingResult.reviewRequired,
             FindingNextAction.requestReviewBeforeOpening),
            (FindingSeverity.critical, FindingResult.blocking,
             FindingNextAction.stopOpening),
        )
        for severity, outcome, action in variants:
            with self.subTest(severity=severity):
                result = ExplainedFinding(AnalysisFinding(
                    FindingCode.activeContent, severity, object_number=23, page_number=4
                ))
                self.assertIs(result.result, outcome)
                self.assertIs(result.next_action, action)
                self.assertEqual(result.to_dict()["objectNumber"], 23)
                self.assertEqual(result.to_dict()["pageNumber"], 4)
                self.assertEqual(result.to_dict()["result"]["outcome"], outcome.value)

    def test_inspection_failure_and_limit_cannot_be_downgraded_to_informational(self):
        for code in (FindingCode.inspectionFailure, FindingCode.resourceLimit):
            finding = AnalysisFinding(code, FindingSeverity.informational)
            result = explain_analysis_findings(report_for(finding))
            self.assertFalse(result.source.requires_block)
            self.assertTrue(result.requires_block)
            self.assertEqual(result.to_dict()["stageResults"][0]["findings"][0]["result"],
                             {"outcome": "inspectionIncomplete",
                              "explanation": ExplainedFinding(finding).explanation,
                              "nextAction": "rerunOrRepairInspection"})

    def test_preserves_expected_stage_order_missing_and_incomplete_stages(self):
        finding = AnalysisFinding(FindingCode.unresolvedReference,
                                  FindingSeverity.critical, object_number=17)
        source = StructuredAnalysisFindings(
            (AnalysisStage.pdfStructure, AnalysisStage.objectRelationships,
             AnalysisStage.javascriptActions),
            (StageAnalysis(AnalysisStage.objectRelationships,
                           StageOutcome.incomplete, (finding,)),
             StageAnalysis(AnalysisStage.pdfStructure, StageOutcome.completed)),
        )
        payload = explain_analysis_findings(source).to_dict()
        self.assertEqual([x["stage"] for x in payload["stageResults"]],
                         ["pdfStructure", "objectRelationships", "javascriptActions"])
        self.assertEqual([x["outcome"] for x in payload["stageResults"]],
                         ["completed", "incomplete", "notRun"])
        self.assertEqual([len(x["findings"]) for x in payload["stageResults"]], [0, 1, 0])
        self.assertEqual(payload["stageResults"][1]["findings"][0]["objectNumber"], 17)
        self.assertTrue(payload["requiresBlock"])
        self.assertFalse(payload["authorizesOpen"])

    def test_never_opens_when_no_findings_or_all_informational(self):
        empty = explain_analysis_findings(report_for())
        info = explain_analysis_findings(report_for(
            AnalysisFinding(FindingCode.incrementalRevision,
                            FindingSeverity.informational)))
        for result in (empty, info):
            self.assertFalse(result.requires_block)
            self.assertIs(result.authorizes_open, False)
            self.assertIs(result.to_dict()["authorizesOpen"], False)
        self.assertEqual(empty.to_dict()["stageResults"][0]["findings"], [])

    def test_all_findings_remain_distinct_in_order_and_json_is_detached(self):
        originals = (
            AnalysisFinding(FindingCode.suspiciousUrl, FindingSeverity.suspicious,
                            object_number=8),
            AnalysisFinding(FindingCode.suspiciousUrl, FindingSeverity.critical,
                            object_number=9),
        )
        original = report_for(*originals)
        enriched = explain_analysis_findings(original)
        before = original.to_dict()
        output = json.loads(json.dumps(enriched.to_dict()))
        self.assertEqual(output["schemaVersion"], 2)
        self.assertEqual(original.to_dict(), before)
        self.assertEqual(original.to_dict()["schemaVersion"], 1)
        self.assertEqual([x["objectNumber"] for x in output["stageResults"][0]["findings"]],
                         [8, 9])
        self.assertEqual([x["result"]["outcome"] for x in output["stageResults"][0]["findings"]],
                         ["reviewRequired", "blocking"])
        output["stageResults"][0]["findings"].clear()
        self.assertEqual(len(enriched.to_dict()["stageResults"][0]["findings"]), 2)

    def test_immutable_inputs_and_invalid_types_fail_closed(self):
        with self.assertRaises(TypeError):
            explain_analysis_findings({"findings": ["/tmp/private"]})
        with self.assertRaises(TypeError):
            ExplainedFinding("arbitrary PDF text")
        entry = ExplainedFinding(AnalysisFinding(FindingCode.activeContent,
                                                 FindingSeverity.critical))
        with self.assertRaises(FrozenInstanceError):
            entry.finding = None
        wrapped = explain_analysis_findings(report_for(entry.finding))
        with self.assertRaises(FrozenInstanceError):
            wrapped.source = None
        self.assertIsInstance(wrapped.stage_findings, tuple)
        self.assertIsInstance(wrapped.stage_findings[0], tuple)

    def test_fixed_text_cannot_echo_untrusted_document_values(self):
        report = report_for(AnalysisFinding(FindingCode.suspiciousUrl,
                                            FindingSeverity.critical))
        serialized = json.dumps(explain_analysis_findings(report).to_dict())
        for private in ("https://private.example/secret", "document.pdf",
                        "/Users/private", "subprocess.run"):
            self.assertNotIn(private, serialized)

    def test_scanner_and_profile_remain_untouched(self):
        scanner = (Path(__file__).parent / "scan-and-open.py").read_text()
        self.assertNotIn("enhanced_finding_explanations", scanner)
        self.assertIn("check_database()", scanner)
        self.assertIn("if not cached_clean(cache_id):", scanner)
        from protection_policy_definitions import PROTECTION_POLICIES, ProtectionProfileID
        self.assertFalse(PROTECTION_POLICIES[ProtectionProfileID.ENHANCED].selectable)


if __name__ == "__main__":
    unittest.main()
