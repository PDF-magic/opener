#!/usr/bin/env python3
"""opener-1039: genuine interactive-form documents in the PDF security corpus."""

from dataclasses import FrozenInstanceError
from io import BytesIO
from pathlib import Path
import unittest
from unittest.mock import patch

from pypdf import PdfReader
from pypdf.generic import StreamObject

from interactive_form_corpus import INTERACTIVE_FORM_PDFS, _document_with_field
from pdf_form_actions import inspect_pdf_form_actions
from pdf_unsupported_feature_inspection import (
    UnsupportedPDFFeature, inspect_pdf_unsupported_features,
)
from pdf_xfa_forms import inspect_pdf_xfa_forms
from reference_pdf_collection import REFERENCE_PDFS

ROOT = Path(__file__).resolve().parents[2]


class InteractiveFormCorpusTests(unittest.TestCase):
    def test_distinct_reproducible_real_pdf_documents(self):
        self.assertEqual(
            [sample.identifier for sample in INTERACTIVE_FORM_PDFS],
            ["acroform-text", "acroform-checkbox", "acroform-choice"],
        )
        self.assertEqual(len({sample.content for sample in INTERACTIVE_FORM_PDFS}), 3)
        for sample in INTERACTIVE_FORM_PDFS:
            with self.subTest(sample=sample.identifier):
                self.assertIs(type(sample.content), bytes)
                self.assertLess(len(sample.content), 64 * 1024)
                self.assertTrue(sample.content.startswith(b"%PDF-"))
                self.assertTrue(sample.content.rstrip().endswith(b"%%EOF"))
                kind = sample.identifier.split("-")[-1]
                self.assertEqual(sample.content, _document_with_field(kind))
                with self.assertRaises(FrozenInstanceError):
                    sample.content = b"other PDF"

                reader = PdfReader(BytesIO(sample.content), strict=True)
                self.assertFalse(reader.is_encrypted)
                self.assertEqual(len(reader.pages), 1)
                form = reader.trailer["/Root"]["/AcroForm"].get_object()
                self.assertIs(form["/NeedAppearances"].value, False)
                self.assertEqual(len(form["/Fields"]), 1)
                field = form["/Fields"][0].get_object()
                self.assertEqual(field["/FT"], sample.field_type)
                self.assertEqual(str(field["/V"]), sample.field_value)
                self.assertEqual(len(reader.get_fields()), 1)

                annotations = reader.pages[0]["/Annots"]
                self.assertEqual(len(annotations), 1)
                widget = annotations[0].get_object()
                self.assertEqual(widget["/Subtype"], "/Widget")
                self.assertEqual(field["/Kids"][0], annotations[0])
                self.assertEqual(widget["/Parent"].get_object(), field)
                self.assertEqual(widget["/P"].get_object(), reader.pages[0])
                normal = widget["/AP"]["/N"]

                if kind == "checkbox":
                    self.assertEqual(widget["/AS"], "/Yes")
                    self.assertEqual(set(normal), {"/Off", "/Yes"})
                    streams = normal.values()
                else:
                    self.assertIsInstance(normal.get_object(), StreamObject)
                    streams = (normal,)
                for appearance in streams:
                    stream = appearance.get_object()
                    self.assertEqual(stream["/Subtype"], "/Form")
                    self.assertGreater(len(stream.get_data()), 20)
                if kind == "choice":
                    self.assertEqual(field["/Ff"] & (1 << 17), 1 << 17)
                    self.assertEqual(list(field["/Opt"]), ["Option A", "Option B"])

    def test_passive_inspection_identifies_forms_without_open_authorization(self):
        with (
            patch("subprocess.Popen", side_effect=AssertionError("process launched")) as process,
            patch("socket.create_connection", side_effect=AssertionError("network used")) as network,
        ):
            for sample in INTERACTIVE_FORM_PDFS:
                with self.subTest(sample=sample.identifier):
                    feature_report = inspect_pdf_unsupported_features(sample.content)
                    self.assertIn(
                        UnsupportedPDFFeature.INTERACTIVE_FORMS, feature_report.feature_codes
                    )
                    self.assertIn(
                        UnsupportedPDFFeature.ANNOTATIONS, feature_report.feature_codes
                    )
                    self.assertFalse(feature_report.inspection_complete)
                    self.assertFalse(feature_report.authorizes_open)
                    self.assertFalse(feature_report.to_dict()["authorizesOpen"])
                    self.assertNotIn(sample.field_value, repr(feature_report))

                    actions = inspect_pdf_form_actions(sample.content)
                    self.assertEqual(actions.action_count, 0)
                    self.assertFalse(actions.permits_open)
                    xfa = inspect_pdf_xfa_forms(sample.content)
                    self.assertFalse(xfa.contains_xfa)
                    self.assertFalse(xfa.permits_open)
                    for forbidden in (
                        b"/JavaScript", b"/OpenAction", b"/SubmitForm",
                        b"/ImportData", b"/Launch", b"/XFA", b"/EmbeddedFiles",
                    ):
                        self.assertNotIn(forbidden, sample.content)
        process.assert_not_called()
        network.assert_not_called()

    def test_isolated_corpus_preserves_six_baselines_and_scanner_boundary(self):
        self.assertEqual(len(REFERENCE_PDFS), 6)
        self.assertTrue(
            {sample.identifier for sample in INTERACTIVE_FORM_PDFS}.isdisjoint(
                sample.identifier for sample in REFERENCE_PDFS
            )
        )
        scanner = (ROOT / "scan-and-open.py").read_text(encoding="utf-8")
        self.assertIn("if not cached_clean(cache_id):", scanner)
        self.assertNotIn("interactive_form_corpus", scanner)
        workflow = (ROOT / ".github/workflows/pdf-interactive-form-corpus.yml").read_text(
            encoding="utf-8"
        )
        self.assertIn(
            "PYTHONPATH=. python3 tests/pdf/interactive-form-corpus.py -v",
            workflow,
        )


if __name__ == "__main__":
    unittest.main()
