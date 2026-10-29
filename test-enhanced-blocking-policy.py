#!/usr/bin/env python3
"""opener-0300: explicit, monotonic blocking decisions for Enhanced findings."""

from dataclasses import FrozenInstanceError
import json
from pathlib import Path
import unittest

from enhanced_analysis_findings import (
    AnalysisFinding, AnalysisStage, FindingCode, FindingSeverity,
    StageAnalysis, StageOutcome, StructuredAnalysisFindings,
)
from enhanced_additional_inspections import plan_additional_inspections
from enhanced_inconclusive_results import assess_inconclusive_opening
from enhanced_blocking_policy import (
    BlockingDisposition, EnhancedBlockingPolicy, FindingBlockingDecision,
    determine_blocking_findings, disposition_for_finding,
)


def report(*findings, stage=AnalysisStage.pdfStructure,
           outcome=StageOutcome.completed):
    return StructuredAnalysisFindings(
        (stage,), (StageAnalysis(stage, outcome, findings),)
    )


class EnhancedBlockingPolicyTests(unittest.TestCase):
    def test_exhaustive_matrix_all_codes_and_severities(self):
        denial_codes = {
            FindingCode.malformedStructure,
            FindingCode.conflictingStructure,
            FindingCode.unresolvedReference,
            FindingCode.unsupportedFeature,
            FindingCode.resourceLimit,
            FindingCode.inspectionFailure,
        }
        review_codes = {
            FindingCode.activeContent,
            FindingCode.suspiciousUrl,
            FindingCode.unexpectedEmbeddedFile,
        }
        routine_codes = {FindingCode.incrementalRevision}
        self.assertEqual(denial_codes | review_codes | routine_codes,
                         set(FindingCode))
        for code in FindingCode:
            for severity in FindingSeverity:
                with self.subTest(code=code, severity=severity):
                    item = AnalysisFinding(code, severity)
                    disposition = disposition_for_finding(item)
                    expected = (
                        BlockingDisposition.denyOpening
                        if code in denial_codes or severity is FindingSeverity.critical
                        else BlockingDisposition.holdForReview
                        if code in review_codes or severity is FindingSeverity.suspicious
                        else BlockingDisposition.observation
                    )
                    self.assertIs(disposition, expected)
                    decision = determine_blocking_findings(report(item))
                    self.assertIs(decision.findings[0].disposition, expected)
                    self.assertEqual(decision.findings[0].requires_block,
                                     expected is not BlockingDisposition.observation)
                    self.assertFalse(decision.authorizes_open)

    def test_low_severity_cannot_downgrade_unresolved_or_risky_codes(self):
        for code in FindingCode:
            if code is FindingCode.incrementalRevision:
                continue
            with self.subTest(code=code):
                source = report(AnalysisFinding(code, FindingSeverity.informational))
                decision = determine_blocking_findings(source)
                self.assertFalse(source.requires_block)
                self.assertTrue(decision.requires_block)
                self.assertTrue(decision.blocking_findings)

    def test_ordinary_revision_is_only_an_observation_not_a_pass(self):
        decision = determine_blocking_findings(
            report(AnalysisFinding(
                FindingCode.incrementalRevision, FindingSeverity.informational))
        )
        self.assertFalse(decision.requires_block)
        self.assertEqual(decision.blocking_findings, ())
        self.assertEqual(
            decision.findings[0].disposition, BlockingDisposition.observation)
        self.assertIs(decision.to_dict()["authorizesOpen"], False)
        self.assertNotIn("clean", decision.to_dict())

    def test_missing_and_incomplete_stages_always_block_without_findings(self):
        source = StructuredAnalysisFindings(
            (AnalysisStage.pdfStructure, AnalysisStage.embeddedUrls,
             AnalysisStage.embeddedFiles),
            (StageAnalysis(AnalysisStage.pdfStructure, StageOutcome.completed),
             StageAnalysis(AnalysisStage.embeddedFiles, StageOutcome.incomplete)),
        )
        decision = determine_blocking_findings(source)
        self.assertEqual(
            decision.incomplete_stages,
            (AnalysisStage.embeddedUrls, AnalysisStage.embeddedFiles),
        )
        self.assertTrue(decision.requires_block)
        self.assertEqual(decision.findings, ())
        self.assertEqual(decision.to_dict()["incompleteStages"],
                         ["embeddedUrls", "embeddedFiles"])

    def test_duplicate_findings_order_and_locations_are_preserved(self):
        source = StructuredAnalysisFindings(
            (AnalysisStage.embeddedUrls, AnalysisStage.pdfStructure),
            (
                StageAnalysis(
                    AnalysisStage.pdfStructure, StageOutcome.completed,
                    (AnalysisFinding(FindingCode.malformedStructure,
                                     FindingSeverity.critical, object_number=31),)),
                StageAnalysis(
                    AnalysisStage.embeddedUrls, StageOutcome.completed,
                    (AnalysisFinding(FindingCode.suspiciousUrl,
                                     FindingSeverity.suspicious, page_number=7),
                     AnalysisFinding(FindingCode.suspiciousUrl,
                                     FindingSeverity.critical, page_number=8))),
            ),
        )
        decision = determine_blocking_findings(source)
        self.assertEqual(
            [(x.source_stage.value, x.finding.code.value,
              x.disposition.value) for x in decision.findings],
            [("embeddedUrls", "suspiciousUrl", "holdForReview"),
             ("embeddedUrls", "suspiciousUrl", "denyOpening"),
             ("pdfStructure", "malformedStructure", "denyOpening")],
        )
        payload = decision.to_dict()
        self.assertEqual(
            [x["pageNumber"] for x in payload["findings"]], [7, 8, None])
        self.assertEqual(payload["findings"][2]["objectNumber"], 31)

    def test_prior_fail_closed_policies_are_never_weakened(self):
        samples = (
            report(),
            report(AnalysisFinding(FindingCode.incrementalRevision,
                                   FindingSeverity.informational)),
            report(AnalysisFinding(FindingCode.activeContent,
                                   FindingSeverity.informational)),
            report(AnalysisFinding(FindingCode.inspectionFailure,
                                   FindingSeverity.informational)),
            report(AnalysisFinding(FindingCode.incrementalRevision,
                                   FindingSeverity.suspicious)),
            report(outcome=StageOutcome.incomplete),
            StructuredAnalysisFindings((AnalysisStage.pdfStructure,)),
        )
        for source in samples:
            with self.subTest(report=source.to_dict()):
                outcome = determine_blocking_findings(source)
                earlier = assess_inconclusive_opening(source)
                followup = plan_additional_inspections(source)
                self.assertTrue(
                    outcome.requires_block or not earlier.requires_block)
                self.assertTrue(
                    outcome.requires_block or not followup.requires_block)
                self.assertTrue(
                    outcome.requires_block or not source.requires_block)
                self.assertFalse(outcome.authorizes_open)

    def test_invalid_inputs_and_forged_json_cannot_bypass_policy(self):
        for invalid in (None, {}, [], "clean", {"requiresBlock": False}):
            with self.subTest(input=type(invalid)):
                with self.assertRaises(TypeError):
                    determine_blocking_findings(invalid)
                with self.assertRaises(TypeError):
                    disposition_for_finding(invalid)
        finding = AnalysisFinding(FindingCode.activeContent,
                                  FindingSeverity.informational)
        with self.assertRaises(TypeError):
            FindingBlockingDecision("pdfStructure", finding)
        with self.assertRaises(TypeError):
            FindingBlockingDecision(AnalysisStage.pdfStructure, "safe")

    def test_results_immutable_and_detached(self):
        source = report(AnalysisFinding(
            FindingCode.suspiciousUrl, FindingSeverity.suspicious,
            object_number=55, page_number=3))
        result = determine_blocking_findings(source)
        with self.assertRaises(FrozenInstanceError):
            result.requires_block = False
        with self.assertRaises(FrozenInstanceError):
            result.findings[0].disposition = BlockingDisposition.observation
        payload = result.to_dict()
        saved = json.loads(json.dumps(payload))
        saved["findings"].clear()
        saved["requiresBlock"] = False
        self.assertEqual(result.to_dict(), payload)
        for secret in ("https://private.invalid/token", "/Users/private/report.pdf",
                       "secret-password", "eval(document)"):
            self.assertNotIn(secret, json.dumps(result.to_dict()))

    def test_no_findings_does_not_authorize_an_open(self):
        result = determine_blocking_findings(report())
        self.assertEqual(result.to_dict(), {
            "schemaVersion": 1,
            "requiresBlock": False,
            "authorizesOpen": False,
            "incompleteStages": [],
            "findings": [],
        })

    def test_scanner_user_preferences_and_protection_levels_unchanged(self):
        root = Path(__file__).resolve().parent
        scanner = (root / "scan-and-open.py").read_text()
        policy = (root / "enhanced_blocking_policy.py").read_text()
        self.assertNotIn("enhanced_blocking_policy", scanner)
        self.assertIn("check_database()", scanner)
        self.assertIn("if not cached_clean(cache_id):", scanner)
        self.assertNotIn("launch_clean_file", policy)
        self.assertNotIn("subprocess", policy)
        self.assertNotIn("urllib", policy)
        from protection_policy_definitions import (
            PROTECTION_POLICIES, ProtectionProfileID)
        self.assertFalse(PROTECTION_POLICIES[ProtectionProfileID.ENHANCED].selectable)


if __name__ == "__main__":
    unittest.main()
