#!/usr/bin/env python3
"""opener-0289: passive PDF form-action inspection regressions."""
from dataclasses import FrozenInstanceError
from io import BytesIO
from pathlib import Path
import os
import subprocess
import unittest
from unittest.mock import patch

from pypdf import PdfWriter
from pypdf.generic import (
    ArrayObject, DictionaryObject, NameObject, NumberObject, TextStringObject,
)
from pdf_form_actions import (
    BLOCK_MESSAGE, MAX_PDF_BYTES, PDFFormActionInspectionError,
    inspect_pdf_form_actions,
)


def action(name, **fields):
    obj = DictionaryObject({NameObject("/S"): NameObject("/" + name)})
    for key, value in fields.items():
        obj[NameObject("/" + key)] = value
    return obj


def pdf_with_action(*actions, placement="open", orphan=False):
    writer = PdfWriter()
    page = writer.add_blank_page(width=200, height=200)
    refs = [writer._add_object(a) for a in actions]
    if not orphan:
        if placement == "open":
            writer._root_object[NameObject("/OpenAction")] = refs[0]
        elif placement == "annotation":
            page[NameObject("/Annots")] = ArrayObject([
                writer._add_object(DictionaryObject({
                    NameObject("/Subtype"): NameObject("/Widget"),
                    NameObject("/A"): refs[0],
                }))
            ])
        elif placement == "page":
            page[NameObject("/AA")] = DictionaryObject({NameObject("/O"): refs[0]})
    output = BytesIO()
    writer.write(output)
    return output.getvalue()


class PDFFormActionTests(unittest.TestCase):
    def test_reference_collection_has_no_form_actions(self):
        from reference_pdf_collection import REFERENCE_PDFS
        for sample in REFERENCE_PDFS:
            with self.subTest(pdf=sample.identifier):
                report = inspect_pdf_form_actions(sample.content)
                self.assertEqual(report.action_count, 0)
                self.assertFalse(report.has_form_actions)
                self.assertFalse(report.permits_open)
                with self.assertRaises(FrozenInstanceError):
                    report.permits_open = True

    def test_submit_form_target_not_leaked_or_invoked(self):
        secret = "https://sensitive.invalid/collect"
        fields = ArrayObject([TextStringObject("private-field")])
        document = pdf_with_action(action("SubmitForm", F=TextStringObject(secret),
                                             Fields=fields, Flags=NumberObject(4)))
        with patch.object(os, "system") as shell, patch.object(subprocess, "run") as run:
            result = inspect_pdf_form_actions(document)
        self.assertEqual(result.action_count, 1)
        self.assertEqual(result.action_kinds, ("submit",))
        self.assertEqual(result.field_selector_count, 1)
        self.assertTrue(result.has_submission_target)
        self.assertNotIn("sensitive", repr(result))
        self.assertNotIn("private-field", repr(result))
        shell.assert_not_called()
        run.assert_not_called()

    def test_reset_import_and_chained_actions(self):
        reset = action("ResetForm", Fields=ArrayObject([TextStringObject("Form.Name")]),
                       Flags=NumberObject(1))
        reset[NameObject("/Next")] = ArrayObject([
            action("ImportData", F=DictionaryObject({
                NameObject("/UF"): TextStringObject("private-data.fdf")
            })),
            action("SubmitForm", F=TextStringObject("https://hidden.invalid")),
        ])
        report = inspect_pdf_form_actions(pdf_with_action(reset, placement="page"))
        self.assertEqual(report.action_count, 3)
        self.assertEqual(report.action_kinds, ("import", "reset", "submit"))
        self.assertEqual(report.field_selector_count, 1)

    def test_annotation_and_orphan_indirect_actions_are_detected(self):
        reset = action("ResetForm")
        self.assertEqual(inspect_pdf_form_actions(
            pdf_with_action(reset, placement="annotation")).action_kinds, ("reset",))
        self.assertEqual(inspect_pdf_form_actions(
            pdf_with_action(action("ResetForm"), orphan=True)).action_count, 1)

    def test_non_form_actions_are_not_misclassified(self):
        result = inspect_pdf_form_actions(pdf_with_action(
            action("URI", URI=TextStringObject("https://example.invalid"))))
        self.assertEqual(result.action_count, 0)

    def test_invalid_form_action_parameters_fail_closed(self):
        bad = (
            action("SubmitForm"),
            action("SubmitForm", F=ArrayObject()),
            action("ImportData", F=TextStringObject("")),
            action("SubmitForm", F=TextStringObject("ok"), Fields=TextStringObject("not array")),
            action("SubmitForm", F=TextStringObject("ok"), Fields=ArrayObject([NumberObject(7)])),
            action("ResetForm", Flags=TextStringObject("1")),
            action("ResetForm", Flags=NumberObject(2)),
            action("SubmitForm", F=TextStringObject("ok"), Flags=NumberObject(-1)),
            action("ImportData", F=TextStringObject("ok"), Fields=ArrayObject()),
            action("ResetForm", Next=ArrayObject([NumberObject(123)])),
        )
        for sample in bad:
            with self.subTest(action=repr(sample)[:80]):
                with self.assertRaises(PDFFormActionInspectionError) as error:
                    inspect_pdf_form_actions(pdf_with_action(sample))
                self.assertEqual(str(error.exception), BLOCK_MESSAGE)

    def test_malformed_truncated_encrypted_oversize_fail_closed(self):
        inputs = (b"", b"not a pdf", b"%PDF-1.5\ntruncated", "not bytes",
                  b"%PDF" * (MAX_PDF_BYTES // 4 + 1))
        for contents in inputs:
            with self.subTest(size=len(contents)):
                with self.assertRaises(PDFFormActionInspectionError) as error:
                    inspect_pdf_form_actions(contents)
                self.assertEqual(str(error.exception), BLOCK_MESSAGE)
        writer = PdfWriter()
        writer.add_blank_page(width=200, height=200)
        writer.encrypt("password")
        output = BytesIO()
        writer.write(output)
        with self.assertRaises(PDFFormActionInspectionError):
            inspect_pdf_form_actions(output.getvalue())
        pdf = pdf_with_action(action("ResetForm"))
        with self.assertRaises(PDFFormActionInspectionError):
            inspect_pdf_form_actions(pdf[:-15])

    def test_existing_built_in_scanner_is_unchanged(self):
        scanner = (Path(__file__).resolve().parent / "scan-and-open.py").read_text()
        self.assertNotIn("pdf_form_actions", scanner)
        self.assertIn("if not cached_clean(cache_id):", scanner)
        self.assertIn("remove_quarantine(path)", scanner)
        from protection_policy_definitions import PROTECTION_POLICIES, ProtectionProfileID
        self.assertFalse(PROTECTION_POLICIES[ProtectionProfileID.ENHANCED].selectable)


if __name__ == "__main__":
    unittest.main()
