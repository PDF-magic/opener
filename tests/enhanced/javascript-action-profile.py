#!/usr/bin/env python3
"""opener-1014: test a real JavaScript-bearing PDF against planned Enhanced safeguards.

Enhanced is not an executable profile. This regression verifies its passive
JavaScript evidence and fail-closed admission contract, not a live Enhanced
malware scan or an authorization to open a file.
"""

from io import BytesIO
from pathlib import Path
import unittest
from unittest.mock import patch

from pypdf import PdfWriter
from pypdf.generic import DictionaryObject, NameObject, TextStringObject

from effective_protection_policy import (
    SELECTED_PROFILE_KEY, UnsupportedEffectivePolicy, resolve_effective_policy,
)
from enhanced_analysis_findings import (
    AnalysisFinding, AnalysisStage, FindingCode, FindingSeverity, StageAnalysis,
    StageOutcome, StructuredAnalysisFindings,
)
from enhanced_blocking_policy import (
    BlockingDisposition, determine_blocking_findings,
)
from pdf_javascript_actions import (
    PDFJavaScriptInspectionError, inspect_pdf_javascript_actions,
)
from protection_policy_definitions import (
    ControlAvailability, FailureDisposition, PROTECTION_POLICIES,
    PolicyControl,
)
from protection_profiles import ProtectionProfileID, PROTECTION_PROFILES
from reference_pdf_collection import REFERENCE_PDFS


ROOT = Path(__file__).resolve().parents[2]


def pdf_with_open_javascript(script: str) -> bytes:
    """Serialize real PDF objects; the supplied script is never run."""
    writer = PdfWriter()
    writer.add_blank_page(width=612, height=792)
    action = DictionaryObject({
        NameObject("/S"): NameObject("/JavaScript"),
        NameObject("/JS"): TextStringObject(script),
    })
    writer._root_object[NameObject("/OpenAction")] = writer._add_object(action)
    output = BytesIO()
    writer.write(output)
    return output.getvalue()


class EnhancedJavaScriptActionProfileTests(unittest.TestCase):
    def test_javascript_pdf_reports_inert_evidence_never_open_permission(self):
        script = 'app.launchURL("https://example.invalid"); eval("never run");'
        contents = pdf_with_open_javascript(script)
        self.assertTrue(contents.startswith(b"%PDF-"))
        self.assertIn(b"/JavaScript", contents)
        self.assertIn(b"/OpenAction", contents)

        # A parser may inspect the serialized action but must not launch it.
        with patch("subprocess.Popen", side_effect=AssertionError("script executed")) as launch:
            evidence = inspect_pdf_javascript_actions(contents)
            launch.assert_not_called()
        self.assertEqual(evidence.action_count, 1)
        self.assertEqual(evidence.total_script_bytes, len(script.encode("utf-8")))
        self.assertEqual(evidence.trigger_types, ("document_open",))
        self.assertEqual(evidence.payload_types, ("text",))
        self.assertEqual(evidence.api_reference_hints, ("dynamic_execution", "network"))
        self.assertTrue(evidence.contains_javascript)
        self.assertFalse(evidence.permits_open)
        self.assertNotIn(script, repr(evidence))
        self.assertNotIn("example.invalid", repr(evidence))

    def test_even_javascript_without_risk_hints_is_not_cleared(self):
        evidence = inspect_pdf_javascript_actions(
            pdf_with_open_javascript('app.alert("Inert demonstration");')
        )
        self.assertEqual(evidence.action_count, 1)
        self.assertEqual(evidence.api_reference_hints, ())
        self.assertFalse(evidence.permits_open)
        self.assertFalse(
            inspect_pdf_javascript_actions(REFERENCE_PDFS[0].content).permits_open
        )

    def test_uninspectable_javascript_is_fail_closed(self):
        with self.assertRaises(PDFJavaScriptInspectionError) as caught:
            inspect_pdf_javascript_actions(pdf_with_open_javascript(""))
        self.assertIn("opening was stopped", str(caught.exception))
        self.assertNotIn("/OpenAction", str(caught.exception))

    def test_enhanced_cannot_be_selected_even_for_inspected_javascript_pdf(self):
        contents = pdf_with_open_javascript('app.alert("not approved");')
        self.assertTrue(inspect_pdf_javascript_actions(contents).contains_javascript)
        enhanced = PROTECTION_POLICIES[ProtectionProfileID.ENHANCED]
        self.assertFalse(enhanced.selectable)
        self.assertFalse(PROTECTION_PROFILES[ProtectionProfileID.ENHANCED].selectable)
        self.assertIs(enhanced.failure_disposition, FailureDisposition.DENY)
        self.assertIn(
            (PolicyControl.PDF_STRUCTURE_VALIDATION, ControlAvailability.PLANNED),
            {(requirement.control, requirement.availability)
             for requirement in enhanced.requirements},
        )

        # Reject unsupported selection *before* any scanner or opening attempt.
        with patch("subprocess.Popen", side_effect=AssertionError("scan started")) as scan:
            with self.assertRaises(UnsupportedEffectivePolicy):
                resolve_effective_policy({SELECTED_PROFILE_KEY: "enhanced"})
            scan.assert_not_called()
        self.assertEqual(resolve_effective_policy().profile_id, "built-in")
        self.assertNotIn(
            "pdf_javascript_actions",
            (ROOT / "scan-and-open.py").read_text(encoding="utf-8"),
        )

    def test_modeled_active_content_finding_requires_review_not_opening(self):
        # This is a policy contract, not an assertion that the inactive Enhanced
        # pipeline automatically maps the passive inspector into a scan verdict.
        finding = AnalysisFinding(
            FindingCode.activeContent, FindingSeverity.reviewRequired
        )
        report = StructuredAnalysisFindings(
            (AnalysisStage.pdfStructure,),
            (StageAnalysis(
                AnalysisStage.pdfStructure, StageOutcome.completed, (finding,)
            ),),
        )
        decision = determine_blocking_findings(report)
        self.assertTrue(decision.requires_block)
        self.assertIs(
            decision.findings[0].disposition, BlockingDisposition.holdForReview
        )
        self.assertFalse(decision.authorizes_open)


if __name__ == "__main__":
    unittest.main()
