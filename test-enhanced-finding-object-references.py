#!/usr/bin/env python3
"""Regressions for generation-aware PDF object references on findings."""

from pathlib import Path
import json
import unittest

from enhanced_analysis_findings import (
    AnalysisFinding, AnalysisStage, FindingCode, FindingSeverity,
    MAX_PDF_OBJECT_GENERATION, StageAnalysis, StageOutcome,
    StructuredAnalysisFindings,
)
from enhanced_finding_explanations import explain_analysis_findings


ROOT = Path(__file__).resolve().parent


class FindingObjectReferenceTests(unittest.TestCase):
    def finding(self, **kwargs):
        return AnalysisFinding(
            FindingCode.suspiciousUrl,
            FindingSeverity.suspicious,
            **kwargs,
        )

    def test_complete_reference_is_attached_to_structured_and_explained_findings(self):
        finding = self.finding(
            object_number=42, page_number=2, object_generation_number=3,
        )
        expected = {"objectNumber": 42, "generationNumber": 3}
        self.assertEqual(finding.object_reference, expected)
        self.assertEqual(finding.to_dict()["objectReference"], expected)
        self.assertEqual(finding.to_dict()["objectNumber"], 42)
        self.assertEqual(finding.to_dict()["findingId"],
                         "finding-v1:suspiciousUrl:object=42:page=2")

        report = StructuredAnalysisFindings(
            (AnalysisStage.embeddedUrls,),
            (StageAnalysis(AnalysisStage.embeddedUrls, StageOutcome.completed,
                           (finding,)),),
        )
        structured = json.loads(json.dumps(report.to_dict()))
        explained = json.loads(json.dumps(
            explain_analysis_findings(report).to_dict()
        ))
        self.assertEqual(
            structured["stageResults"][0]["findings"][0]["objectReference"],
            expected,
        )
        self.assertEqual(
            explained["stageResults"][0]["findings"][0]["objectReference"],
            expected,
        )
        self.assertFalse(structured["authorizesOpen"])
        self.assertFalse(explained["authorizesOpen"])

    def test_missing_generation_never_invents_a_complete_reference(self):
        with_number = self.finding(object_number=42)
        without_location = self.finding()
        self.assertEqual(with_number.to_dict()["objectNumber"], 42)
        self.assertNotIn("objectReference", with_number.to_dict())
        self.assertIsNone(with_number.object_reference)
        self.assertNotIn("objectReference", without_location.to_dict())
        self.assertIsNone(without_location.object_reference)

    def test_generation_zero_and_upper_bound_are_valid(self):
        for generation in (0, MAX_PDF_OBJECT_GENERATION):
            with self.subTest(generation=generation):
                finding = self.finding(
                    object_number=7, object_generation_number=generation,
                )
                self.assertEqual(
                    finding.to_dict()["objectReference"],
                    {"objectNumber": 7, "generationNumber": generation},
                )

    def test_invalid_generation_and_unpaired_reference_are_rejected(self):
        for generation in (True, -1, MAX_PDF_OBJECT_GENERATION + 1, "0", 0.0):
            with self.subTest(generation=generation), self.assertRaises(ValueError):
                self.finding(object_number=7, object_generation_number=generation)
        with self.assertRaises(ValueError):
            self.finding(object_generation_number=0)

    def test_reference_output_is_detached_and_scanner_policy_is_unchanged(self):
        finding = self.finding(object_number=12, object_generation_number=0)
        output = finding.to_dict()
        output["objectReference"]["generationNumber"] = 65535
        self.assertEqual(finding.to_dict()["objectReference"]["generationNumber"], 0)
        scanner = (ROOT / "scan-and-open.py").read_text(encoding="utf-8")
        workflow = (ROOT / ".github/workflows/finding-object-references.yml").read_text(
            encoding="utf-8"
        )
        self.assertNotIn("enhanced_finding_object_references", scanner)
        self.assertIn("test-enhanced-finding-object-references.py -v", workflow)
        self.assertFalse(StructuredAnalysisFindings(
            (AnalysisStage.embeddedUrls,),
            (StageAnalysis(AnalysisStage.embeddedUrls, StageOutcome.completed,
                           (finding,)),),
        ).to_dict()["authorizesOpen"])


if __name__ == "__main__":
    unittest.main()
