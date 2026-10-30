#!/usr/bin/env python3
"""opener-0298: legitimate PDF features do not mask dangerous behaviors."""

from dataclasses import FrozenInstanceError
from io import BytesIO
from pathlib import Path
import subprocess
import unittest
from unittest.mock import patch

from pypdf import PdfWriter
from pypdf.generic import ArrayObject, DictionaryObject, NameObject, TextStringObject

from pdf_behavior_classification import (
    BLOCK_MESSAGE, MAX_OBSERVATIONS, BehaviorClassificationError,
    PDFBehaviorAnalysis, PDFBehaviorDisposition, PDFBehaviorKind,
    PDFBehaviorObservation, PDFBehaviorTrigger,
    classify_external_action_inspection, classify_pdf_behavior,
)
from pdf_external_launch_actions import (
    PDFExternalLaunchInspection, inspect_pdf_external_launch_actions,
)


def real_pdf_with_actions(*actions):
    writer = PdfWriter()
    page = writer.add_blank_page(width=200, height=200)
    if actions:
        annotation = DictionaryObject({
            NameObject("/Subtype"): NameObject("/Link"),
            NameObject("/A"): writer._add_object(actions[0]),
        })
        page[NameObject("/Annots")] = ArrayObject([writer._add_object(annotation)])
        for action in actions[1:]:
            writer._root_object[NameObject("/OpenAction")] = writer._add_object(action)
    output = BytesIO()
    writer.write(output)
    return output.getvalue()


def action(name, target):
    return DictionaryObject({
        NameObject("/S"): NameObject("/" + name),
        NameObject("/URI" if name == "URI" else "/F"): TextStringObject(target),
    })


def observe(kind, trigger=PDFBehaviorTrigger.UNKNOWN):
    return PDFBehaviorObservation(kind, trigger)


class PDFBehaviorClassificationTests(unittest.TestCase):
    def test_empty_evidence_is_unassessed_not_clean(self):
        analysis = classify_pdf_behavior(())
        self.assertIs(analysis.highest_disposition, PDFBehaviorDisposition.UNASSESSED)
        self.assertEqual(analysis.findings, ())
        self.assertFalse(analysis.permits_open)
        self.assertFalse(analysis.pdf_is_clean)
        self.assertFalse(analysis.has_dangerous_behavior)

    def test_ordinary_features_remain_legitimate_not_executable(self):
        features = (
            PDFBehaviorKind.INTERNAL_NAVIGATION, PDFBehaviorKind.BOOKMARK,
            PDFBehaviorKind.TEXT_ANNOTATION, PDFBehaviorKind.FORM_FIELD,
            PDFBehaviorKind.FILE_ATTACHMENT,
        )
        analysis = classify_pdf_behavior(tuple(observe(kind) for kind in features))
        self.assertEqual(
            {finding.disposition for finding in analysis.findings},
            {PDFBehaviorDisposition.LEGITIMATE_FEATURE},
        )
        self.assertIs(analysis.highest_disposition,
                      PDFBehaviorDisposition.LEGITIMATE_FEATURE)
        self.assertFalse(analysis.permits_open)
        self.assertFalse(analysis.pdf_is_clean)

    def test_user_link_is_not_an_executable_launch(self):
        clicked = classify_pdf_behavior((
            observe(PDFBehaviorKind.URI_LINK, PDFBehaviorTrigger.USER),
            observe(PDFBehaviorKind.EMBEDDED_NAVIGATION, PDFBehaviorTrigger.USER),
        ))
        unknown = classify_pdf_behavior((observe(PDFBehaviorKind.URI_LINK),))
        self.assertIs(clicked.highest_disposition,
                      PDFBehaviorDisposition.LEGITIMATE_FEATURE)
        self.assertIs(unknown.highest_disposition,
                      PDFBehaviorDisposition.REQUIRES_REVIEW)
        self.assertFalse(clicked.permits_open)

    def test_automatic_external_actions_are_dangerous_not_ordinary_links(self):
        for kind in (PDFBehaviorKind.URI_LINK, PDFBehaviorKind.REMOTE_NAVIGATION,
                     PDFBehaviorKind.FORM_SUBMISSION, PDFBehaviorKind.FORM_IMPORT):
            with self.subTest(kind=kind):
                assessment = classify_pdf_behavior((
                    observe(kind, PDFBehaviorTrigger.AUTOMATIC),
                ))
                self.assertIs(assessment.highest_disposition,
                              PDFBehaviorDisposition.DANGEROUS_BEHAVIOR)
                self.assertTrue(assessment.has_dangerous_behavior)

    def test_interactive_form_submission_and_script_are_not_assumed_safe(self):
        analysis = classify_pdf_behavior((
            observe(PDFBehaviorKind.FORM_SUBMISSION, PDFBehaviorTrigger.USER),
            observe(PDFBehaviorKind.FORM_IMPORT, PDFBehaviorTrigger.USER),
            observe(PDFBehaviorKind.JAVASCRIPT_ACTION, PDFBehaviorTrigger.USER),
            observe(PDFBehaviorKind.JAVASCRIPT_ACTION, PDFBehaviorTrigger.AUTOMATIC),
        ))
        self.assertEqual({finding.disposition for finding in analysis.findings},
                         {PDFBehaviorDisposition.REQUIRES_REVIEW})

    def test_privileged_script_and_launch_dominate_legitimate_features(self):
        for dangerous in (
            PDFBehaviorKind.EXECUTABLE_LAUNCH, PDFBehaviorKind.SCRIPT_NETWORK_ACCESS,
            PDFBehaviorKind.SCRIPT_FILE_ACCESS, PDFBehaviorKind.SCRIPT_DYNAMIC_EXECUTION,
        ):
            with self.subTest(dangerous=dangerous):
                analysis = classify_pdf_behavior((
                    observe(PDFBehaviorKind.TEXT_ANNOTATION),
                    observe(PDFBehaviorKind.FORM_FIELD),
                    observe(dangerous, PDFBehaviorTrigger.USER),
                ))
                self.assertIs(analysis.highest_disposition,
                              PDFBehaviorDisposition.DANGEROUS_BEHAVIOR)
                self.assertTrue(analysis.has_dangerous_behavior)
                self.assertFalse(analysis.permits_open)

    def test_real_pdf_uri_annotation_is_review_not_malware_claim(self):
        payload = real_pdf_with_actions(action("URI", "https://private.invalid/path"))
        with patch.object(subprocess, "run") as process:
            report = inspect_pdf_external_launch_actions(payload)
            analysis = classify_external_action_inspection(report)
        process.assert_not_called()
        self.assertEqual(report.action_kinds, ("uri",))
        self.assertIs(analysis.highest_disposition,
                      PDFBehaviorDisposition.REQUIRES_REVIEW)
        self.assertEqual(analysis.findings[0].kind, PDFBehaviorKind.URI_LINK)
        self.assertNotIn("private.invalid", repr(analysis))
        self.assertFalse(analysis.pdf_is_clean)

    def test_real_pdf_executable_launch_outweighs_hyperlink(self):
        payload = real_pdf_with_actions(
            action("URI", "https://ordinary.example/resource"),
            action("Launch", "C:/private/program.exe"),
        )
        report = inspect_pdf_external_launch_actions(payload)
        analysis = classify_external_action_inspection(report)
        self.assertEqual(report.action_count, 2)
        self.assertIs(analysis.highest_disposition,
                      PDFBehaviorDisposition.DANGEROUS_BEHAVIOR)
        self.assertIn(PDFBehaviorKind.EXECUTABLE_LAUNCH,
                      [finding.kind for finding in analysis.findings])
        self.assertNotIn("program.exe", repr(analysis))
        self.assertFalse(analysis.permits_open)

    def test_reference_pdfs_are_unassessed_not_certified_clean(self):
        from reference_pdf_collection import REFERENCE_PDFS
        for sample in REFERENCE_PDFS:
            with self.subTest(sample=sample.identifier):
                analysis = classify_external_action_inspection(
                    inspect_pdf_external_launch_actions(sample.content))
                self.assertFalse(analysis.permits_open)
                self.assertFalse(analysis.pdf_is_clean)

    def test_invalid_and_oversized_findings_fail_closed_without_private_text(self):
        invalid = (
            [], ["../private/secret.pdf"], (object(),),
            (observe(PDFBehaviorKind.BOOKMARK),) * (MAX_OBSERVATIONS + 1),
        )
        for evidence in invalid:
            with self.subTest(evidence_type=type(evidence)):
                with self.assertRaises(BehaviorClassificationError) as error:
                    classify_pdf_behavior(evidence)
                self.assertEqual(str(error.exception), BLOCK_MESSAGE)
                self.assertNotIn("secret.pdf", str(error.exception))
        with self.assertRaises(BehaviorClassificationError):
            PDFBehaviorObservation("javascript_action")
        with self.assertRaises(BehaviorClassificationError):
            PDFBehaviorObservation(PDFBehaviorKind.BOOKMARK, "user")
        with self.assertRaises(BehaviorClassificationError):
            classify_external_action_inspection({"action_kinds": ["launch"]})

    def test_reports_cannot_grant_open_permission_or_mutate_findings(self):
        analysis = classify_pdf_behavior((observe(PDFBehaviorKind.BOOKMARK),))
        with self.assertRaises(FrozenInstanceError):
            analysis.permits_open = True
        with self.assertRaises(BehaviorClassificationError):
            PDFBehaviorAnalysis((), PDFBehaviorDisposition.UNASSESSED,
                                permits_open=True)
        with self.assertRaises(BehaviorClassificationError):
            PDFBehaviorAnalysis((), PDFBehaviorDisposition.UNASSESSED,
                                pdf_is_clean=True)
        with self.assertRaises(FrozenInstanceError):
            analysis.findings[0].disposition = PDFBehaviorDisposition.LEGITIMATE_FEATURE

    def test_built_in_gate_and_saved_preferences_remain_untouched(self):
        root = Path(__file__).resolve().parents[2]
        scanner = (root / "scan-and-open.py").read_text()
        self.assertNotIn("pdf_behavior_classification", scanner)
        self.assertIn("if not cached_clean(cache_id):", scanner)
        self.assertIn("remove_quarantine(path)", scanner)
        from protection_policy_definitions import PROTECTION_POLICIES, ProtectionProfileID
        self.assertFalse(PROTECTION_POLICIES[ProtectionProfileID.ENHANCED].selectable)


if __name__ == "__main__":
    unittest.main()
