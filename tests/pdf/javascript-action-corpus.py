#!/usr/bin/env python3
"""opener-1036: actual, inert JavaScript-action PDFs in the security corpus."""

from dataclasses import FrozenInstanceError
from io import BytesIO
from pathlib import Path
import unittest
from unittest.mock import patch

from pypdf import PdfReader
from pypdf.generic import DictionaryObject

from javascript_action_corpus import (
    JAVASCRIPT_ACTION_PDFS, _document_with_action,
)
from pdf_automatic_actions import inspect_pdf_automatic_actions
from pdf_javascript_actions import inspect_pdf_javascript_actions
from reference_pdf_collection import REFERENCE_PDFS


ROOT = Path(__file__).resolve().parents[2]


class JavaScriptActionCorpusTests(unittest.TestCase):
    def test_real_pdf_documents_and_reproducible_distinct_fixtures(self):
        self.assertEqual(len(JAVASCRIPT_ACTION_PDFS), 3)
        self.assertEqual(len({sample.identifier for sample in JAVASCRIPT_ACTION_PDFS}), 3)
        self.assertEqual(len({sample.content for sample in JAVASCRIPT_ACTION_PDFS}), 3)
        for sample in JAVASCRIPT_ACTION_PDFS:
            with self.subTest(sample=sample.identifier):
                self.assertIs(type(sample.content), bytes)
                self.assertLess(len(sample.content), 64 * 1024)
                self.assertTrue(sample.content.startswith(b"%PDF-"))
                self.assertIn(b"/JavaScript", sample.content)
                self.assertIn(b"/JS", sample.content)
                self.assertEqual(len(PdfReader(BytesIO(sample.content), strict=True).pages), 1)
                with self.assertRaises(FrozenInstanceError):
                    sample.content = b"replaced"

        self.assertEqual(
            JAVASCRIPT_ACTION_PDFS[0].content,
            _document_with_action("open", "app.alert('Inert PDF fixture'); eval('0');"),
        )

    def test_action_hooks_and_payloads_are_real_pdf_objects(self):
        open_pdf = PdfReader(BytesIO(JAVASCRIPT_ACTION_PDFS[0].content), strict=True)
        open_action = open_pdf.trailer["/Root"]["/OpenAction"].get_object()
        self.assertIsInstance(open_action, DictionaryObject)
        self.assertEqual(open_action["/S"], "/JavaScript")
        self.assertIn("Inert PDF fixture", open_action["/JS"])

        page_pdf = PdfReader(BytesIO(JAVASCRIPT_ACTION_PDFS[1].content), strict=True)
        self.assertEqual(page_pdf.pages[0]["/AA"]["/O"]["/S"], "/JavaScript")

        tree_pdf = PdfReader(BytesIO(JAVASCRIPT_ACTION_PDFS[2].content), strict=True)
        entry = tree_pdf.trailer["/Root"]["/Names"]["/JavaScript"]["/Names"]
        self.assertEqual(entry[0], "InertExample")
        self.assertEqual(entry[1].get_object()["/S"], "/JavaScript")
        self.assertTrue(entry[1].get_object()["/JS"].get_object().get_data())

    def test_inspect_but_never_execute_or_authorize_javascript(self):
        with (patch("subprocess.Popen", side_effect=AssertionError("process launched")) as process,
              patch("socket.create_connection", side_effect=AssertionError("network accessed")) as network):
            for sample in JAVASCRIPT_ACTION_PDFS:
                with self.subTest(sample=sample.identifier):
                    actions = inspect_pdf_automatic_actions(sample.content)
                    scripts = inspect_pdf_javascript_actions(sample.content)
                    self.assertEqual(actions.action_count, 1)
                    self.assertEqual(actions.action_types, ("JavaScript",))
                    self.assertEqual(actions.trigger_types, (sample.expected_trigger,))
                    self.assertEqual(scripts.action_count, 1)
                    self.assertEqual(scripts.trigger_types, (sample.expected_trigger,))
                    self.assertEqual(scripts.payload_types, (sample.expected_payload_type,))
                    self.assertEqual(scripts.api_reference_hints, sample.expected_hints)
                    self.assertGreater(scripts.total_script_bytes, 0)
                    self.assertTrue(scripts.contains_javascript)
                    self.assertFalse(actions.permits_open)
                    self.assertFalse(scripts.permits_open)
                    self.assertNotIn("example.invalid", repr(scripts))
                    self.assertNotIn("InertFixture", repr(scripts))
            process.assert_not_called()
            network.assert_not_called()

    def test_clean_baselines_and_active_scanner_remain_unmodified(self):
        self.assertTrue(set(sample.identifier for sample in JAVASCRIPT_ACTION_PDFS)
                        .isdisjoint(sample.identifier for sample in REFERENCE_PDFS))
        for sample in REFERENCE_PDFS:
            with self.subTest(sample=sample.identifier):
                self.assertEqual(inspect_pdf_javascript_actions(sample.content).action_count, 0)
        self.assertNotIn("javascript_action_corpus", (ROOT / "scan-and-open.py").read_text())
        self.assertNotIn("javascript_action_corpus", (ROOT / "effective_protection_policy.py").read_text())


if __name__ == "__main__":
    unittest.main()
