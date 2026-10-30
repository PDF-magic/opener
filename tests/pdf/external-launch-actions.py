#!/usr/bin/env python3
"""opener-0288: classify external actions without launching a PDF target."""

from dataclasses import FrozenInstanceError
from io import BytesIO
from pathlib import Path
import os
import subprocess
import unittest
from unittest.mock import patch

from pypdf import PdfWriter
from pypdf.generic import (
    ArrayObject, BooleanObject, DictionaryObject, NameObject, TextStringObject,
)
from pdf_external_launch_actions import (
    BLOCK_MESSAGE, MAX_PDF_BYTES, PDFExternalLaunchInspectionError,
    inspect_pdf_external_launch_actions,
)


def pdf_with_actions(*actions, placement="open"):
    writer = PdfWriter()
    page = writer.add_blank_page(width=612, height=792)
    references = [writer._add_object(action) for action in actions]
    if placement == "open":
        writer._root_object[NameObject("/OpenAction")] = references[0]
    elif placement == "page":
        page[NameObject("/AA")] = DictionaryObject({
            NameObject("/O"): references[0],
        })
    elif placement == "annotation":
        annotation = DictionaryObject({
            NameObject("/Subtype"): NameObject("/Link"),
            NameObject("/A"): references[0],
        })
        page[NameObject("/Annots")] = ArrayObject([writer._add_object(annotation)])
    else:
        raise AssertionError("invalid fixture placement")
    output = BytesIO()
    writer.write(output)
    return output.getvalue()


def action(kind, **fields):
    dictionary = DictionaryObject({NameObject("/S"): NameObject("/" + kind)})
    for key, value in fields.items():
        dictionary[NameObject("/" + key)] = value
    return dictionary


class PDFExternalLaunchTests(unittest.TestCase):
    def test_reference_pdf_collection_has_no_external_actions(self):
        from reference_pdf_collection import REFERENCE_PDFS
        for sample in REFERENCE_PDFS:
            with self.subTest(pdf=sample.identifier):
                result = inspect_pdf_external_launch_actions(sample.content)
                self.assertEqual(result.action_count, 0)
                self.assertFalse(result.has_external_actions)
                self.assertFalse(result.permits_open)
                with self.assertRaises(FrozenInstanceError):
                    result.permits_open = True

    def test_launch_file_target_classified_without_execution_or_leaks(self):
        target = "C:/Private/secret-command.exe"
        pdf = pdf_with_actions(action("Launch", F=TextStringObject(target)))
        with patch.object(os, "system") as shell, patch.object(subprocess, "run") as run:
            result = inspect_pdf_external_launch_actions(pdf)
        self.assertEqual(result.action_count, 1)
        self.assertEqual(result.action_kinds, ("launch",))
        self.assertEqual(result.target_kinds, ("file",))
        self.assertNotIn(target, repr(result))
        self.assertFalse(result.permits_open)
        shell.assert_not_called()
        run.assert_not_called()

    def test_windows_command_target_in_link_annotation(self):
        win = DictionaryObject({
            NameObject("/F"): TextStringObject("secret.exe"),
            NameObject("/P"): TextStringObject("--sensitive"),
        })
        report = inspect_pdf_external_launch_actions(
            pdf_with_actions(action("Launch", Win=win), placement="annotation")
        )
        self.assertEqual(report.action_kinds, ("launch",))
        self.assertEqual(report.target_kinds, ("windows_command",))
        self.assertNotIn("sensitive", repr(report))

    def test_remote_uri_and_form_actions_with_next_array(self):
        remote = action("GoToR", F=TextStringObject("private.pdf"),
                        D=TextStringObject("destination"),
                        NewWindow=BooleanObject(True))
        remote[NameObject("/Next")] = ArrayObject([
            action("URI", URI=TextStringObject("https://secret.invalid/path")),
            action("SubmitForm", F=TextStringObject("https://private.invalid")),
        ])
        report = inspect_pdf_external_launch_actions(
            pdf_with_actions(remote, placement="page")
        )
        self.assertEqual(report.action_count, 3)
        self.assertEqual(report.action_kinds, ("remote_goto", "submit_form", "uri"))
        self.assertEqual(report.target_kinds, ("file", "form", "uri"))
        self.assertNotIn("private.invalid", repr(report))

    def test_embedded_navigation_and_import_data_with_next_dictionary(self):
        embedded = action("GoToE", D=TextStringObject("destination"))
        embedded[NameObject("/Next")] = action(
            "ImportData", F=TextStringObject("private.csv")
        )
        report = inspect_pdf_external_launch_actions(pdf_with_actions(embedded))
        self.assertEqual(report.action_count, 2)
        self.assertEqual(report.action_kinds, ("embedded_goto", "import_data"))

    def test_orphaned_indirect_action_is_detected(self):
        writer = PdfWriter()
        writer.add_blank_page(width=100, height=100)
        writer._add_object(action("Launch", F=TextStringObject("private.exe")))
        output = BytesIO()
        writer.write(output)
        self.assertEqual(
            inspect_pdf_external_launch_actions(output.getvalue()).action_count, 1
        )

    def test_invalid_action_targets_fail_closed_without_leaks(self):
        samples = (
            action("Launch"),
            action("Launch", F=ArrayObject()),
            action("Launch", Win=DictionaryObject()),
            action("GoToR", F=TextStringObject("foo")),
            action("URI"),
            action("SubmitForm"),
            action("Launch", F=TextStringObject("foo"),
                   NewWindow=TextStringObject("bad")),
        )
        for bad_action in samples:
            with self.subTest(kind=str(bad_action["/S"])):
                with self.assertRaises(PDFExternalLaunchInspectionError) as error:
                    inspect_pdf_external_launch_actions(pdf_with_actions(bad_action))
                self.assertEqual(str(error.exception), BLOCK_MESSAGE)

    def test_encrypted_malformed_and_oversize_pdfs_fail_closed(self):
        samples = (
            b"garbage", b"", b"%PDF-1.7\ntruncated", "not bytes",
            b"%PDF" * (MAX_PDF_BYTES // 4 + 1),
        )
        for sample in samples:
            with self.subTest(size=len(sample)):
                with self.assertRaises(PDFExternalLaunchInspectionError) as error:
                    inspect_pdf_external_launch_actions(sample)
                self.assertEqual(str(error.exception), BLOCK_MESSAGE)
        writer = PdfWriter()
        writer.add_blank_page(width=100, height=100)
        writer.encrypt("password")
        output = BytesIO()
        writer.write(output)
        with self.assertRaises(PDFExternalLaunchInspectionError):
            inspect_pdf_external_launch_actions(output.getvalue())

    def test_truncated_indirect_structure_is_not_accepted(self):
        pdf = pdf_with_actions(
            action("Launch", F=TextStringObject("private.exe"))
        )
        with self.assertRaises(PDFExternalLaunchInspectionError):
            inspect_pdf_external_launch_actions(pdf[:-15])

    def test_no_changes_to_built_in_scanning_or_preferences(self):
        root = Path(__file__).resolve().parent
        scanner = (root / "scan-and-open.py").read_text()
        self.assertNotIn("pdf_external_launch_actions", scanner)
        self.assertIn("if not cached_clean(cache_id):", scanner)
        self.assertIn("remove_quarantine(path)", scanner)
        from protection_policy_definitions import PROTECTION_POLICIES, ProtectionProfileID
        self.assertFalse(PROTECTION_POLICIES[ProtectionProfileID.ENHANCED].selectable)


if __name__ == "__main__":
    unittest.main()
