#!/usr/bin/env python3
"""Real PDF action inspection regressions; never run embedded PDF scripts."""
import builtins
from dataclasses import FrozenInstanceError
from io import BytesIO
from pathlib import Path
import unittest
from unittest.mock import patch

from pypdf import PdfWriter
from pypdf.generic import (
    ArrayObject, DictionaryObject, NameObject, TextStringObject, NumberObject,
)

from pdf_automatic_actions import (
    MAX_ACTIONS, PDFAutomaticActionError, PDFAutomaticActionInspection,
    inspect_pdf_automatic_actions,
)
from reference_pdf_collection import REFERENCE_PDFS


ROOT = Path(__file__).resolve().parent


def pdf(writer):
    out = BytesIO()
    writer.write(out)
    return out.getvalue()


def writer_with_page():
    writer = PdfWriter()
    writer.add_blank_page(width=612, height=792)
    return writer


def js_action(script="app.alert('never execute')"):
    return DictionaryObject({
        NameObject("/S"): NameObject("/JavaScript"),
        NameObject("/JS"): TextStringObject(script),
    })


class PDFAutomaticActionTests(unittest.TestCase):
    def test_reference_pdfs_have_no_automatic_actions_and_are_immutable(self):
        for sample in REFERENCE_PDFS:
            with self.subTest(sample=sample.identifier):
                evidence = inspect_pdf_automatic_actions(sample.content)
                self.assertEqual(evidence, PDFAutomaticActionInspection(
                    action_count=0, open_destination_count=0,
                    trigger_types=(), action_types=()))
                self.assertFalse(evidence.has_automatic_actions)
                self.assertFalse(evidence.permits_open)
                with self.assertRaises(FrozenInstanceError):
                    evidence.action_count = 5

    def test_catalog_open_action_detects_script_without_evaluating_it(self):
        writer = writer_with_page()
        writer._root_object[NameObject("/OpenAction")] = writer._add_object(
            js_action("app.launchURL('https://private.example')"))
        evidence = inspect_pdf_automatic_actions(pdf(writer))
        self.assertEqual(evidence.action_count, 1)
        self.assertEqual(evidence.action_types, ("JavaScript",))
        self.assertEqual(evidence.trigger_types, ("document_open",))
        self.assertNotIn("private.example", repr(evidence))
        self.assertFalse(evidence.permits_open)

    def test_open_destination_is_distinct_from_script(self):
        writer = writer_with_page()
        writer._root_object[NameObject("/OpenAction")] = ArrayObject([
            writer.pages[0].indirect_reference, NameObject("/Fit"),
        ])
        evidence = inspect_pdf_automatic_actions(pdf(writer))
        self.assertEqual(evidence.action_count, 0)
        self.assertEqual(evidence.open_destination_count, 1)
        self.assertEqual(evidence.trigger_types, ("document_open_destination",))

    def test_document_and_page_additional_actions_are_detected(self):
        writer = writer_with_page()
        writer._root_object[NameObject("/AA")] = DictionaryObject({
            NameObject("/WC"): writer._add_object(js_action("secret-contents")),
        })
        writer.pages[0][NameObject("/AA")] = DictionaryObject({
            NameObject("/O"): DictionaryObject({
                NameObject("/S"): NameObject("/URI"),
                NameObject("/URI"): TextStringObject("https://sensitive.invalid"),
            }),
        })
        evidence = inspect_pdf_automatic_actions(pdf(writer))
        self.assertEqual(evidence.action_count, 2)
        self.assertEqual(evidence.action_types, ("JavaScript", "URI"))
        self.assertEqual(evidence.trigger_types,
                         ("document_additional", "page_additional"))
        self.assertNotIn("sensitive.invalid", repr(evidence))

    def test_document_javascript_name_tree_is_inspected(self):
        writer = writer_with_page()
        leaf = DictionaryObject({
            NameObject("/Names"): ArrayObject([
                TextStringObject("private-token"),
                writer._add_object(js_action()),
            ]),
        })
        writer._root_object[NameObject("/Names")] = DictionaryObject({
            NameObject("/JavaScript"): DictionaryObject({
                NameObject("/Kids"): ArrayObject([writer._add_object(leaf)]),
            }),
        })
        evidence = inspect_pdf_automatic_actions(pdf(writer))
        self.assertEqual(evidence.action_count, 1)
        self.assertEqual(evidence.trigger_types, ("document_javascript",))
        self.assertEqual(evidence.action_types, ("JavaScript",))
        self.assertNotIn("private-token", repr(evidence))

    def test_annotation_and_form_fields_extra_actions_are_inspected(self):
        writer = writer_with_page()
        annot = DictionaryObject({
            NameObject("/Type"): NameObject("/Annot"),
            NameObject("/Subtype"): NameObject("/Widget"),
            NameObject("/Rect"): ArrayObject([NumberObject(0)] * 4),
            NameObject("/AA"): DictionaryObject({
                NameObject("/E"): js_action(),
            }),
        })
        writer.pages[0][NameObject("/Annots")] = ArrayObject([
            writer._add_object(annot),
        ])
        field = DictionaryObject({
            NameObject("/FT"): NameObject("/Tx"),
            NameObject("/AA"): DictionaryObject({
                NameObject("/K"): js_action(),
            }),
        })
        writer._root_object[NameObject("/AcroForm")] = DictionaryObject({
            NameObject("/Fields"): ArrayObject([writer._add_object(field)]),
        })
        evidence = inspect_pdf_automatic_actions(pdf(writer))
        self.assertEqual(evidence.action_count, 2)
        self.assertEqual(evidence.trigger_types,
                         ("annotation_additional", "field_additional"))

    def test_chained_actions_are_inspected_and_not_executed(self):
        writer = writer_with_page()
        chain = js_action()
        chain[NameObject("/Next")] = writer._add_object(DictionaryObject({
            NameObject("/S"): NameObject("/Launch"),
            NameObject("/F"): TextStringObject("untrusted-command"),
        }))
        writer._root_object[NameObject("/OpenAction")] = writer._add_object(chain)
        evidence = inspect_pdf_automatic_actions(pdf(writer))
        self.assertEqual(evidence.action_count, 2)
        self.assertEqual(evidence.action_types, ("JavaScript", "Launch"))
        self.assertNotIn("untrusted-command", repr(evidence))

    def test_malformed_action_and_name_tree_fail_closed(self):
        cases = (
            {"/S": "/JavaScript"},  # Script payload absent.
            {"/S": "/JavaScript", "/JS": 12},  # Script payload invalid.
            {"/S": "/URI", "/Next": 17},  # Broken chain.
            {"/JS": "incomplete"},  # Action type missing.
        )
        for raw in cases:
            with self.subTest(raw=raw):
                writer = writer_with_page()
                act = DictionaryObject()
                for key, value in raw.items():
                    act[NameObject(key)] = (
                        NameObject(value) if key == "/S" else
                        TextStringObject(value) if isinstance(value, str) else
                        NumberObject(value)
                    )
                writer._root_object[NameObject("/OpenAction")] = act
                with self.assertRaises(PDFAutomaticActionError) as error:
                    inspect_pdf_automatic_actions(pdf(writer))
                self.assertIn("opening was stopped", str(error.exception))
        writer = writer_with_page()
        writer._root_object[NameObject("/Names")] = DictionaryObject({
            NameObject("/JavaScript"): DictionaryObject({
                NameObject("/Names"): ArrayObject([TextStringObject("odd")]),
            })
        })
        with self.assertRaises(PDFAutomaticActionError):
            inspect_pdf_automatic_actions(pdf(writer))

    def test_excessive_chains_and_cycle_fail_closed(self):
        writer = writer_with_page()
        chain = [js_action() for _ in range(MAX_ACTIONS + 1)]
        # Limit the serialized PDF size while still exceeding action count.
        writer._root_object[NameObject("/OpenAction")] = DictionaryObject({
            NameObject("/S"): NameObject("/Named"),
            NameObject("/Next"): ArrayObject(chain),
        })
        with self.assertRaises(PDFAutomaticActionError):
            inspect_pdf_automatic_actions(pdf(writer))
        writer = writer_with_page()
        cycle = js_action()
        reference = writer._add_object(cycle)
        cycle[NameObject("/Next")] = reference
        writer._root_object[NameObject("/OpenAction")] = reference
        with self.assertRaises(PDFAutomaticActionError):
            inspect_pdf_automatic_actions(pdf(writer))

    def test_encrypted_broken_oversized_and_invalid_types_fail_closed(self):
        writer = writer_with_page()
        writer.encrypt("fixture-password")
        for contents in (
            pdf(writer), b"%PDF-1.4\n%%EOF\n", b"invalid",
            b"z" * (16 * 1024 * 1024 + 1),
            None, "PDF", bytearray(REFERENCE_PDFS[0].content),
        ):
            with self.subTest(kind=type(contents).__name__):
                with self.assertRaises(PDFAutomaticActionError) as error:
                    inspect_pdf_automatic_actions(contents)
                self.assertIn("opening was stopped", str(error.exception))
                self.assertNotIn("fixture-password", str(error.exception))

    def test_missing_pypdf_fails_closed_without_import_on_module_load(self):
        original = builtins.__import__
        def missing(name, *args, **kwargs):
            if name == "pypdf":
                raise ModuleNotFoundError("missing parser")
            return original(name, *args, **kwargs)
        with patch("builtins.__import__", side_effect=missing):
            with self.assertRaises(PDFAutomaticActionError):
                inspect_pdf_automatic_actions(REFERENCE_PDFS[0].content)

    def test_no_scanner_activation_or_user_preference_mutation(self):
        scanner = (ROOT / "scan-and-open.py").read_text(encoding="utf-8")
        module = (ROOT / "pdf_automatic_actions.py").read_text(encoding="utf-8")
        workflow = (ROOT / ".github/workflows/ci.yml").read_text(encoding="utf-8")
        self.assertNotIn("pdf_automatic_actions", scanner)
        self.assertNotIn("pdf_automatic_actions", (ROOT / "effective_protection_policy.py").read_text())
        for forbidden in (
            "subprocess.", "launch_clean_file(", "remove_quarantine(",
            "UserDefaults", "os.environ", "get_data(", "write_text(", "open(",
        ):
            self.assertNotIn(forbidden, module)
        self.assertIn("python3 test-pdf-automatic-actions.py -v", workflow)
        self.assertIn("python3 test-pdf-structure-parser.py -v", workflow)


if __name__ == "__main__":
    unittest.main()
