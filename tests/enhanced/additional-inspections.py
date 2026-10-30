#!/usr/bin/env python3
"""Focused regression tests for opener-0301 follow-up inspection policy."""

from dataclasses import FrozenInstanceError
import json
from pathlib import Path
import unittest

from enhanced_analysis_findings import (
    AnalysisFinding, AnalysisStage, FindingCode, FindingSeverity, StageAnalysis,
    StageOutcome, StructuredAnalysisFindings,
)
from enhanced_additional_inspections import (
    AdditionalInspectionPlan, FindingInspectionRequirement, FollowUpInspection,
    plan_additional_inspections,
)


def report(*findings, stage=AnalysisStage.pdfStructure,
           outcome=StageOutcome.completed):
    return StructuredAnalysisFindings(
        (stage,), (StageAnalysis(stage, outcome, findings),)
    )


class AdditionalInspectionPolicyTests(unittest.TestCase):
    def test_exact_followup_table_covers_every_diagnostic_code(self):
        expected = {
            FindingCode.malformedStructure: ("validateStructure", "inspectObjectRelationships"),
            FindingCode.conflictingStructure: ("inspectObjectRelationships", "inspectRevisionHistory"),
            FindingCode.unresolvedReference: ("inspectObjectRelationships",),
            FindingCode.knownMaliciousContent: (),
            FindingCode.activeContent: ("inspectActiveActions",),
            FindingCode.suspiciousUrl: ("inspectEmbeddedUrls",),
            FindingCode.unexpectedEmbeddedFile: ("inspectEmbeddedFiles",
                                                  "inspectEmbeddedExecutables"),
            FindingCode.incrementalRevision: ("inspectRevisionHistory",),
            FindingCode.unsupportedFeature: ("reviewUnsupportedFeature",),
            FindingCode.resourceLimit: ("reviewResourceLimits", "retryFailedInspection"),
            FindingCode.inspectionFailure: ("retryFailedInspection",),
        }
        self.assertEqual(set(expected), set(FindingCode))
        for code, checks in expected.items():
            with self.subTest(code=code):
                finding = AnalysisFinding(code, FindingSeverity.suspicious)
                entry = FindingInspectionRequirement(AnalysisStage.pdfStructure, finding)
                self.assertEqual(tuple(x.value for x in entry.required_inspections), checks)
                self.assertEqual(entry.requires_additional_inspection, bool(checks))
                self.assertTrue(plan_additional_inspections(report(finding)).requires_block)

    def test_known_malicious_content_is_terminal_and_still_blocks(self):
        for severity in FindingSeverity:
            with self.subTest(severity=severity):
                plan = plan_additional_inspections(report(AnalysisFinding(
                    FindingCode.knownMaliciousContent, severity,
                )))
                self.assertEqual(plan.required_inspections, ())
                self.assertFalse(plan.requires_additional_inspection)
                self.assertTrue(plan.requires_block)
                self.assertFalse(plan.authorizes_open)
                self.assertTrue(plan.to_dict()["requiresBlock"])

    def test_informational_incremental_revision_does_not_automatically_trigger(self):
        normal = AnalysisFinding(FindingCode.incrementalRevision,
                                 FindingSeverity.informational)
        routine = plan_additional_inspections(report(normal))
        self.assertEqual(routine.required_inspections, ())
        self.assertFalse(routine.requires_additional_inspection)
        self.assertFalse(routine.requires_block)
        self.assertFalse(routine.authorizes_open)
        entry = routine.to_dict()["findingRequirements"][0]
        self.assertFalse(entry["requiresAdditionalInspection"])
        self.assertEqual(entry["requiredInspections"], [])
        for severity in (FindingSeverity.suspicious, FindingSeverity.critical):
            with self.subTest(severity=severity):
                raised = plan_additional_inspections(report(
                    AnalysisFinding(FindingCode.incrementalRevision, severity)
                ))
                self.assertEqual(raised.required_inspections,
                                 (FollowUpInspection.inspectRevisionHistory,))
                self.assertTrue(raised.requires_block)

    def test_low_severity_risk_findings_still_require_followup(self):
        for code in (FindingCode.activeContent, FindingCode.suspiciousUrl,
                     FindingCode.malformedStructure, FindingCode.unexpectedEmbeddedFile,
                     FindingCode.unsupportedFeature, FindingCode.resourceLimit,
                     FindingCode.inspectionFailure):
            with self.subTest(code=code):
                source = report(AnalysisFinding(code, FindingSeverity.informational))
                plan = plan_additional_inspections(source)
                self.assertTrue(plan.requires_additional_inspection)
                self.assertTrue(plan.requires_block)
                self.assertFalse(plan.to_dict()["authorizesOpen"])

    def test_missing_and_incomplete_stages_need_retry_with_no_findings(self):
        source = StructuredAnalysisFindings(
            (AnalysisStage.pdfStructure, AnalysisStage.embeddedFiles,
             AnalysisStage.javascriptActions),
            (StageAnalysis(AnalysisStage.pdfStructure, StageOutcome.completed),
             StageAnalysis(AnalysisStage.embeddedFiles, StageOutcome.incomplete)),
        )
        plan = plan_additional_inspections(source)
        self.assertEqual(plan.incomplete_stages,
                         (AnalysisStage.embeddedFiles, AnalysisStage.javascriptActions))
        self.assertEqual(plan.required_inspections,
                         (FollowUpInspection.retryIncompleteStage,))
        self.assertTrue(plan.requires_block)
        output = plan.to_dict()
        self.assertEqual(output["incompleteStages"], ["embeddedFiles", "javascriptActions"])
        self.assertEqual(output["findingRequirements"], [])
        self.assertTrue(output["requiresAdditionalInspection"])

    def test_completed_discovery_stage_cannot_satisfy_followup_by_itself(self):
        # An embedded URL already discovered by the URL inspector still needs
        # further assessment: no completion is inferred from discovery.
        source = report(AnalysisFinding(FindingCode.suspiciousUrl,
                                        FindingSeverity.informational),
                        stage=AnalysisStage.embeddedUrls)
        plan = plan_additional_inspections(source)
        self.assertEqual(plan.incomplete_stages, ())
        self.assertEqual(plan.required_inspections,
                         (FollowUpInspection.inspectEmbeddedUrls,))
        self.assertTrue(plan.requires_additional_inspection)
        self.assertTrue(plan.requires_block)

    def test_deduplicates_summary_but_not_individual_finding_evidence(self):
        findings = (
            AnalysisFinding(FindingCode.suspiciousUrl, FindingSeverity.suspicious,
                            object_number=3),
            AnalysisFinding(FindingCode.suspiciousUrl, FindingSeverity.critical,
                            object_number=5),
            AnalysisFinding(FindingCode.unexpectedEmbeddedFile, FindingSeverity.informational,
                            page_number=2),
        )
        plan = plan_additional_inspections(report(*findings))
        self.assertEqual(plan.required_inspections, (
            FollowUpInspection.inspectEmbeddedUrls,
            FollowUpInspection.inspectEmbeddedFiles,
            FollowUpInspection.inspectEmbeddedExecutables,
        ))
        entries = plan.to_dict()["findingRequirements"]
        self.assertEqual(len(entries), 3)
        self.assertEqual([x["objectNumber"] for x in entries], [3, 5, None])
        self.assertEqual(entries[-1]["pageNumber"], 2)
        self.assertEqual(entries[0]["sourceStage"], "pdfStructure")

    def test_output_stage_order_is_from_trusted_policy_not_input_order(self):
        a = AnalysisFinding(FindingCode.activeContent, FindingSeverity.suspicious)
        b = AnalysisFinding(FindingCode.unresolvedReference, FindingSeverity.critical)
        source = StructuredAnalysisFindings(
            (AnalysisStage.pdfStructure, AnalysisStage.javascriptActions),
            (StageAnalysis(AnalysisStage.javascriptActions, StageOutcome.completed, (a,)),
             StageAnalysis(AnalysisStage.pdfStructure, StageOutcome.completed, (b,))),
        )
        plan = plan_additional_inspections(source)
        output = plan.to_dict()
        self.assertEqual([x["sourceStage"] for x in output["findingRequirements"]],
                         ["pdfStructure", "javascriptActions"])
        self.assertEqual([x["code"] for x in output["findingRequirements"]],
                         ["unresolvedReference", "activeContent"])
        self.assertEqual(output["requiredInspections"],
                         ["inspectObjectRelationships", "inspectActiveActions"])
        self.assertFalse(output["authorizesOpen"])

    def test_report_is_immutable_serializable_and_does_not_mutate_contract(self):
        source = report(AnalysisFinding(FindingCode.activeContent,
                                        FindingSeverity.critical, object_number=40))
        original = source.to_dict()
        plan = plan_additional_inspections(source)
        data = json.loads(json.dumps(plan.to_dict()))
        self.assertEqual(data["schemaVersion"], 1)
        self.assertEqual(original, source.to_dict())
        data["findingRequirements"][0]["requiredInspections"].clear()
        self.assertEqual(len(plan.to_dict()["findingRequirements"][0]["requiredInspections"]), 1)
        with self.assertRaises(FrozenInstanceError):
            plan.source = None
        with self.assertRaises(FrozenInstanceError):
            plan.finding_requirements[0].source_stage = None

    def test_bad_types_and_untrusted_values_fail_closed(self):
        with self.assertRaises(TypeError):
            plan_additional_inspections({"stageResults": []})
        with self.assertRaises(TypeError):
            FindingInspectionRequirement("pdfStructure", AnalysisFinding(
                FindingCode.activeContent, FindingSeverity.suspicious))
        with self.assertRaises(TypeError):
            FindingInspectionRequirement(AnalysisStage.pdfStructure, "https://private/")
        with self.assertRaises(TypeError):
            plan_additional_inspections(None)
        with self.assertRaises(TypeError):
            AnalysisFinding("suspiciousUrl", FindingSeverity.suspicious)

    def test_no_document_urls_paths_or_script_text_in_report(self):
        source = report(AnalysisFinding(FindingCode.suspiciousUrl,
                                        FindingSeverity.critical, object_number=9))
        encoded = json.dumps(plan_additional_inspections(source).to_dict())
        for private in ("/Users/private", "secret.pdf", "https://secret.example/",
                        "subprocess.run", "arbitrary document text"):
            self.assertNotIn(private, encoded)
        self.assertNotIn("pdf_is_clean", encoded)
        self.assertIn('"authorizesOpen": false', encoded)

    def test_empty_complete_report_never_authorizes_opening(self):
        plan = plan_additional_inspections(report())
        self.assertFalse(plan.requires_additional_inspection)
        self.assertFalse(plan.requires_block)
        self.assertEqual(plan.finding_requirements, ())
        self.assertIs(plan.authorizes_open, False)
        self.assertFalse(plan.to_dict()["authorizesOpen"])

    def test_deployed_scanner_profiles_and_preferences_remain_separate(self):
        root = Path(__file__).parent
        scanner = (root / "scan-and-open.py").read_text()
        self.assertNotIn("enhanced_additional_inspections", scanner)
        self.assertIn("check_database()", scanner)
        self.assertIn("if not cached_clean(cache_id):", scanner)
        from protection_policy_definitions import PROTECTION_POLICIES, ProtectionProfileID
        self.assertFalse(PROTECTION_POLICIES[ProtectionProfileID.ENHANCED].selectable)


if __name__ == "__main__":
    unittest.main()
