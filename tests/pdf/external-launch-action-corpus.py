#!/usr/bin/env python3
"""opener-1037: actual external /Launch actions in isolated PDF corpus fixtures."""

from dataclasses import FrozenInstanceError
from io import BytesIO
from pathlib import Path
import os
import socket
import subprocess
import unittest
import webbrowser
from unittest.mock import patch

from pypdf import PdfReader
from pypdf.generic import DictionaryObject

from external_launch_action_corpus import EXTERNAL_LAUNCH_PDFS, _document_with_launch
from pdf_automatic_actions import inspect_pdf_automatic_actions
from pdf_external_launch_actions import inspect_pdf_external_launch_actions
from reference_pdf_collection import REFERENCE_PDFS

ROOT = Path(__file__).resolve().parents[2]


class ExternalLaunchActionCorpusTests(unittest.TestCase):
    def test_complete_distinct_deterministic_pdf_documents(self):
        self.assertEqual(len(EXTERNAL_LAUNCH_PDFS), 4)
        self.assertEqual(len({sample.identifier for sample in EXTERNAL_LAUNCH_PDFS}), 4)
        self.assertEqual(len({sample.content for sample in EXTERNAL_LAUNCH_PDFS}), 4)
        for sample in EXTERNAL_LAUNCH_PDFS:
            with self.subTest(pdf=sample.identifier):
                self.assertIs(type(sample.content), bytes)
                self.assertTrue(sample.content.startswith(b"%PDF-"))
                self.assertTrue(sample.content.endswith(b"%%EOF\n"))
                self.assertLess(len(sample.content), 64 * 1024)
                self.assertEqual(len(PdfReader(BytesIO(sample.content), strict=True).pages), 1)
                self.assertEqual(sample.content.count(b"/Launch"), sample.expected_actions)
                self.assertNotIn(b"/JavaScript", sample.content)
                with self.assertRaises(FrozenInstanceError):
                    sample.content = b"changed"
        self.assertEqual(EXTERNAL_LAUNCH_PDFS[0].content,
                         _document_with_launch("open", "file"))

    def test_genuine_launch_dictionaries_and_action_placements(self):
        opened = PdfReader(BytesIO(EXTERNAL_LAUNCH_PDFS[0].content), strict=True)
        action = opened.trailer["/Root"]["/OpenAction"].get_object()
        self.assertIsInstance(action, DictionaryObject)
        self.assertEqual(action["/S"], "/Launch")
        self.assertTrue(action["/F"].endswith(".invalid"))

        page = PdfReader(BytesIO(EXTERNAL_LAUNCH_PDFS[1].content), strict=True)
        action = page.pages[0]["/AA"]["/O"].get_object()
        self.assertEqual(action["/S"], "/Launch")
        self.assertEqual(action["/F"]["/Type"], "/Filespec")
        self.assertTrue(action["/F"]["/UF"].endswith(".invalid"))

        annotated = PdfReader(BytesIO(EXTERNAL_LAUNCH_PDFS[2].content), strict=True)
        link = annotated.pages[0]["/Annots"][0].get_object()
        self.assertEqual(link["/Subtype"], "/Link")
        self.assertEqual(link["/A"]["/S"], "/Launch")
        self.assertTrue(link["/A"]["/Win"]["/F"].endswith(".invalid"))

        chained = PdfReader(BytesIO(EXTERNAL_LAUNCH_PDFS[3].content), strict=True)
        action = chained.trailer["/Root"]["/OpenAction"].get_object()
        self.assertEqual(action["/S"], "/Launch")
        self.assertEqual(action["/Next"].get_object()["/S"], "/Launch")
        self.assertIn("/Win", action["/Next"].get_object())

    def test_passive_inspection_never_launches_or_grants_open_permission(self):
        with (patch.object(os, "system", side_effect=AssertionError("shell invoked")) as shell,
              patch.object(subprocess, "Popen", side_effect=AssertionError("process invoked")) as popen,
              patch.object(subprocess, "run", side_effect=AssertionError("process invoked")) as run,
              patch.object(socket, "create_connection", side_effect=AssertionError("network invoked")) as network,
              patch.object(webbrowser, "open", side_effect=AssertionError("browser invoked")) as browser):
            for sample in EXTERNAL_LAUNCH_PDFS:
                with self.subTest(pdf=sample.identifier):
                    external = inspect_pdf_external_launch_actions(sample.content)
                    automatic = inspect_pdf_automatic_actions(sample.content)
                    self.assertEqual(external.action_count, sample.expected_actions)
                    self.assertEqual(external.action_kinds, ("launch",))
                    self.assertEqual(external.target_kinds, sample.expected_targets)
                    self.assertTrue(external.has_external_actions)
                    self.assertIs(external.permits_open, False)
                    self.assertEqual(automatic.action_count,
                                     sample.expected_actions if sample.expected_trigger else 0)
                    self.assertEqual(automatic.trigger_types,
                                     (sample.expected_trigger,) if sample.expected_trigger else ())
                    self.assertEqual(automatic.action_types,
                                     ("Launch",) if sample.expected_trigger else ())
                    self.assertIs(automatic.permits_open, False)
                    self.assertNotIn("nonexistent-launch-fixture", repr(external))
                    with self.assertRaises(FrozenInstanceError):
                        external.permits_open = True
            shell.assert_not_called()
            popen.assert_not_called()
            run.assert_not_called()
            network.assert_not_called()
            browser.assert_not_called()

    def test_baselines_and_live_scanner_are_unchanged(self):
        self.assertEqual(len(REFERENCE_PDFS), 6)
        self.assertFalse({sample.identifier for sample in REFERENCE_PDFS}
                         & {sample.identifier for sample in EXTERNAL_LAUNCH_PDFS})
        for sample in REFERENCE_PDFS:
            with self.subTest(pdf=sample.identifier):
                self.assertEqual(inspect_pdf_external_launch_actions(sample.content).action_count, 0)
        scanner = (ROOT / "scan-and-open.py").read_text(encoding="utf-8")
        self.assertNotIn("external_launch_action_corpus", scanner)
        self.assertNotIn("EXTERNAL_LAUNCH_PDFS", scanner)


if __name__ == "__main__":
    unittest.main()
