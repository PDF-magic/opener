#!/usr/bin/env python3
"""opener-0302: inconclusive Enhanced evidence must fail closed."""

from dataclasses import FrozenInstanceError
import json
from pathlib import Path
import unittest

from enhanced_analysis_findings import (
    AnalysisFinding, AnalysisStage, FindingCode, FindingSeverity, StageAnalysis,
    StageOutcome, StructuredAnalysisFindings,
)
from enhanced_inconclusive_results import (
    IncompleteStageReason, InconclusiveEvidence, InconclusiveOpeningAssessment,
    InconclusiveOpeningDecision, assess_inconclusive_opening,
)


def report(*findings, stage=AnalysisStage.pdfStructure,
           outcome=StageOutcome.completed):
    return StructuredAnalysisFindings(
        (stage,), (StageAnalysis(stage, outcome, findings),),
    )


class InconclusiveOpeningTests(unittest.TestCase):
    def test_missing_expected_stage_always_blocks_even_with_clean_other_stages(self):
        source = StructuredAnalysisFindings(
            (AnalysisStage.pdfStructure, AnalysisStage.embeddedFiles,
             AnalysisStage.javascriptActions),
            (StageAnalysis(AnalysisStage.pdfStructure, StageOutcome.completed),
             StageAnalysis(AnalysisStage.javascriptActions, StageOutcome.completed)),
        )
        assessment = assess_inconclusive_opening(source)
        self.assertEqual(assessment.decision, InconclusiveOpeningDecision.block)
        self.assertEqual(assessment.evidence, (
            InconclusiveEvidence(AnalysisStage.embeddedFiles,
                                 IncompleteStageReason.notRun),
        ))
        self.assertTrue(assessment.blocks_for_inconclusive)
        self.assertTrue(assessment.requires_block)
        self.assertFalse(assessment.authorizes_open)

    def test_incomplete_stage_blocks_with_no_findings_or_low_severity(self):
        for findings in ((), (AnalysisFinding(
            FindingCode.incrementalRevision, FindingSeverity.informational),)):
            with self.subTest(findings=findings):
                assessment = assess_inconclusive_opening(
                    report(*findings, outcome=StageOutcome.incomplete))
                self.assertEqual(assessment.decision, InconclusiveOpeningDecision.block)
                self.assertEqual(assessment.evidence[0].reason,
                                 IncompleteStageReason.incomplete)
                self.assertEqual(assessment.evidence[0].object_number, None)

    def test_each_unresolved_finding_blocks_even_if_stage_says_completed(self):
        unresolved = {
            FindingCode.malformedStructure,
            FindingCode.conflictingStructure,
            FindingCode.unresolvedReference,
            FindingCode.activeContent,
            FindingCode.suspiciousUrl,
            FindingCode.unexpectedEmbeddedFile,
            FindingCode.unsupportedFeature,
            FindingCode.resourceLimit,
            FindingCode.inspectionFailure,
        }
        self.assertEqual(unresolved | {
            FindingCode.incrementalRevision, FindingCode.knownMaliciousContent,
        }, set(FindingCode))
        for code in unresolved:
            with self.subTest(code=code):
                source = report(AnalysisFinding(
                    code, FindingSeverity.informational,
                    object_number=9, page_number=2))
                assessment = assess_inconclusive_opening(source)
                # The v1 reporting signal alone was not enough for this case.
                self.assertFalse(source.requires_block)
                self.assertTrue(assessment.blocks_for_inconclusive)
                self.assertTrue(assessment.requires_block)
                self.assertEqual(assessment.evidence[0].reason, code)
                self.assertEqual(assessment.evidence[0].object_number, 9)
                self.assertEqual(assessment.evidence[0].page_number, 2)

    def test_known_malicious_content_blocks_without_mislabeling_it_inconclusive(self):
        source = report(AnalysisFinding(
            FindingCode.knownMaliciousContent, FindingSeverity.informational,
        ))
        assessment = assess_inconclusive_opening(source)
        self.assertEqual(assessment.evidence, ())
        self.assertFalse(assessment.blocks_for_inconclusive)
        self.assertTrue(assessment.requires_block)
        self.assertEqual(assessment.decision, InconclusiveOpeningDecision.block)
        self.assertFalse(assessment.authorizes_open)

    def test_informational_incremental_revision_is_not_automatically_inconclusive(self):
        source = report(AnalysisFinding(
            FindingCode.incrementalRevision, FindingSeverity.informational))
        assessment = assess_inconclusive_opening(source)
        self.assertEqual(assessment.evidence, ())
        self.assertFalse(assessment.blocks_for_inconclusive)
        self.assertFalse(assessment.requires_block)
        self.assertEqual(assessment.decision, InconclusiveOpeningDecision.noDecision)
        self.assertIs(assessment.to_dict()["authorizesOpen"], False)
        self.assertNotIn("clean", assessment.to_dict())

    def test_suspicious_or_critical_incremental_revisions_still_block(self):
        for severity in (FindingSeverity.suspicious, FindingSeverity.critical):
            with self.subTest(severity=severity):
                assessment = assess_inconclusive_opening(
                    report(AnalysisFinding(FindingCode.incrementalRevision, severity)))
                self.assertTrue(assessment.blocks_for_inconclusive)
                self.assertTrue(assessment.requires_block)
                self.assertEqual(assessment.evidence[0].reason,
                                 FindingCode.incrementalRevision)

    def test_existing_suspicious_or_critical_gates_are_not_downgraded(self):
        for severity in (FindingSeverity.suspicious, FindingSeverity.critical):
            for code in FindingCode:
                with self.subTest(severity=severity, code=code):
                    assessment = assess_inconclusive_opening(report(
                        AnalysisFinding(code, severity)))
                    self.assertTrue(assessment.requires_block)
                    self.assertEqual(assessment.decision,
                                     InconclusiveOpeningDecision.block)

    def test_incomplete_stage_and_finding_have_distinct_ordered_reasons(self):
        source = StructuredAnalysisFindings(
            (AnalysisStage.pdfStructure, AnalysisStage.embeddedUrls,
             AnalysisStage.embeddedFiles),
            (StageAnalysis(
                AnalysisStage.embeddedUrls, StageOutcome.incomplete,
                (AnalysisFinding(FindingCode.suspiciousUrl,
                                 FindingSeverity.informational, object_number=12),)),
             StageAnalysis(AnalysisStage.pdfStructure, StageOutcome.completed,
                           (AnalysisFinding(FindingCode.unsupportedFeature,
                                            FindingSeverity.informational),))),
        )
        assessment = assess_inconclusive_opening(source)
        self.assertEqual(
            [(x.stage.value, x.reason.value) for x in assessment.evidence],
            [("pdfStructure", "unsupportedFeature"),
             ("embeddedUrls", "incomplete"),
             ("embeddedUrls", "suspiciousUrl"),
             ("embeddedFiles", "notRun")])
        self.assertEqual(assessment.to_dict()["evidence"][2]["objectNumber"], 12)
        self.assertEqual(assessment.to_dict()["decision"], "block")

    def test_no_findings_is_not_a_permission_to_open(self):
        assessment = assess_inconclusive_opening(report())
        self.assertFalse(assessment.blocks_for_inconclusive)
        self.assertFalse(assessment.requires_block)
        self.assertFalse(assessment.authorizes_open)
        self.assertEqual(assessment.to_dict(), {
            "schemaVersion": 1,
            "decision": "noDecision",
            "blocksForInconclusive": False,
            "requiresBlock": False,
            "authorizesOpen": False,
            "evidence": [],
        })

    def test_immutable_validated_inputs_and_no_string_based_bypass(self):
        for invalid in (None, {}, [], "completed", {"requiresBlock": False}):
            with self.subTest(value=str(type(invalid))), self.assertRaises(TypeError):
                assess_inconclusive_opening(invalid)
        for invalid in ("incomplete", None, 0):
            with self.subTest(reason=invalid), self.assertRaises(TypeError):
                InconclusiveEvidence(AnalysisStage.pdfStructure, invalid)
        with self.assertRaises(TypeError):
            InconclusiveEvidence("pdfStructure", IncompleteStageReason.notRun)
        with self.assertRaises(ValueError):
            InconclusiveEvidence(AnalysisStage.pdfStructure,
                                 IncompleteStageReason.incomplete, object_number=3)
        for invalid in (True, -1, 0, 2**31, "11"):
            with self.subTest(location=invalid), self.assertRaises(ValueError):
                InconclusiveEvidence(AnalysisStage.pdfStructure,
                                     FindingCode.unresolvedReference,
                                     object_number=invalid)
        original = report(AnalysisFinding(FindingCode.unsupportedFeature,
                                          FindingSeverity.informational))
        assessment = assess_inconclusive_opening(original)
        with self.assertRaises(FrozenInstanceError):
            assessment.requires_block = False
        with self.assertRaises(FrozenInstanceError):
            assessment.evidence[0].reason = FindingCode.incrementalRevision
        self.assertIsInstance(assessment.evidence, tuple)

    def test_serialization_is_detached_and_never_echoes_pdf_material(self):
        assessment = assess_inconclusive_opening(report(
            AnalysisFinding(FindingCode.suspiciousUrl, FindingSeverity.informational)))
        before = assessment.to_dict()
        payload = json.loads(json.dumps(before))
        payload["evidence"].clear()
        self.assertEqual(assessment.to_dict(), before)
        for sensitive in ("/Users/example/secret.pdf", "https://private.invalid",
                          "print('payload')", "sensitive-form-field"):
            self.assertNotIn(sensitive, json.dumps(before))
        self.assertEqual(assessment.to_dict()["evidence"][0]["stage"], "pdfStructure")

    def test_scanner_quarantine_preferences_and_enhanced_activation_remain_untouched(self):
        root = Path(__file__).resolve().parent
        scanner = (root / "scan-and-open.py").read_text()
        module = (root / "enhanced_inconclusive_results.py").read_text()
        self.assertNotIn("enhanced_inconclusive_results", scanner)
        self.assertIn("if not cached_clean(cache_id):", scanner)
        self.assertIn("remove_quarantine(path)", scanner)
        self.assertNotIn("launch_clean_file", module)
        self.assertNotIn("subprocess", module)
        from protection_policy_definitions import PROTECTION_POLICIES, ProtectionProfileID
        self.assertFalse(PROTECTION_POLICIES[ProtectionProfileID.ENHANCED].selectable)


if __name__ == "__main__":
    unittest.main()
