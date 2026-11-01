#!/usr/bin/env python3
"""opener-1038: exercise real embedded-file PDFs without granting scan approval."""

from dataclasses import FrozenInstanceError
from io import BytesIO
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from pypdf import PdfReader
from pypdf.generic import StreamObject

from embedded_file_corpus import EMBEDDED_FILE_PDFS, _document_with_embedded_files
import enhanced_embedded_files as inspector
from pdf_embedded_file_types import inspect_pdf_embedded_file_types
from reference_pdf_collection import REFERENCE_PDFS


ROOT = Path(__file__).resolve().parents[2]


def _specifications(reader, location):
    catalog = reader.trailer["/Root"]
    if location == "name-tree":
        return catalog["/Names"]["/EmbeddedFiles"]["/Names"][1::2]
    if location == "catalog-associated":
        return catalog["/AF"]
    if location == "page-associated":
        return reader.pages[0]["/AF"]
    if location == "annotation":
        return [annotation.get_object()["/FS"]
                for annotation in reader.pages[0]["/Annots"]]
    raise AssertionError("unexpected fixture")


class EmbeddedFileCorpusTests(unittest.TestCase):
    def test_deterministic_complete_documents_with_distinct_attachment_locations(self):
        self.assertEqual(len(EMBEDDED_FILE_PDFS), 4)
        self.assertEqual(len({sample.identifier for sample in EMBEDDED_FILE_PDFS}), 4)
        self.assertEqual(len({sample.content for sample in EMBEDDED_FILE_PDFS}), 4)
        for sample in EMBEDDED_FILE_PDFS:
            with self.subTest(sample=sample.identifier):
                self.assertIs(type(sample.content), bytes)
                self.assertLess(len(sample.content), 64 * 1024)
                self.assertTrue(sample.content.startswith(b"%PDF-"))
                self.assertIn(b"/EmbeddedFile", sample.content)
                self.assertIn(b"/EF", sample.content)
                reader = PdfReader(BytesIO(sample.content), strict=True)
                self.assertEqual(len(reader.pages), 1)
                self.assertFalse(reader.is_encrypted)
                self.assertEqual("/Names" in reader.trailer["/Root"],
                                 sample.location == "name-tree")
                with self.assertRaises(FrozenInstanceError):
                    sample.content = b"changed"
                self.assertEqual(
                    sample.content,
                    _document_with_embedded_files(sample.location, sample.attachments),
                )

    def test_real_file_specifications_and_exact_embedded_stream_bytes(self):
        for sample in EMBEDDED_FILE_PDFS:
            with self.subTest(sample=sample.identifier):
                reader = PdfReader(BytesIO(sample.content), strict=True)
                specs = _specifications(reader, sample.location)
                self.assertEqual(len(specs), len(sample.attachments))
                for ref, (filename, payload) in zip(specs, sample.attachments):
                    spec = ref.get_object() if hasattr(ref, "get_object") else ref
                    self.assertEqual(spec["/Type"], "/Filespec")
                    self.assertEqual(spec["/F"], filename)
                    stream = spec["/EF"]["/F"].get_object()
                    self.assertIsInstance(stream, StreamObject)
                    self.assertEqual(stream["/Type"], "/EmbeddedFile")
                    self.assertEqual(stream.get_data(), payload)

    def test_passive_inspection_identifies_every_attachment_without_authorization(self):
        with (patch("subprocess.run", side_effect=AssertionError("launched process")) as process,
              patch("socket.create_connection", side_effect=AssertionError("network request")) as network):
            for sample in EMBEDDED_FILE_PDFS:
                with self.subTest(sample=sample.identifier):
                    result = inspect_pdf_embedded_file_types(sample.content)
                    self.assertEqual(result.attachment_count, len(sample.attachments))
                    self.assertEqual(result.inspected_bytes,
                                     sum(len(data) for _, data in sample.attachments))
                    self.assertEqual(result.detected_kinds, ("text",))
                    self.assertEqual(result.executable_count, 0)
                    self.assertFalse(result.authorizes_open)
            process.assert_not_called()
            network.assert_not_called()

    def test_embedded_file_scanning_uses_only_bytes_and_never_clears_pdf(self):
        with tempfile.TemporaryDirectory(prefix="embedded-corpus-") as temporary:
            source = Path(temporary) / "document.pdf"
            database = Path(temporary) / "signatures"
            database.mkdir()
            for sample in EMBEDDED_FILE_PDFS:
                with self.subTest(sample=sample.identifier):
                    source.write_bytes(sample.content)
                    reply = subprocess.CompletedProcess([], 0, b"stream: OK\n", b"")
                    with patch.object(inspector.subprocess, "run", return_value=reply) as scan:
                        result = inspector.inspect_embedded_files(
                            source, "/mock/clamscan", database
                        )
                    self.assertEqual(result.inspected_count, len(sample.attachments))
                    self.assertEqual(result.inspected_bytes,
                                     sum(len(data) for _, data in sample.attachments))
                    self.assertFalse(result.pdf_is_clean)
                    self.assertEqual([call.kwargs["input"] for call in scan.call_args_list],
                                     [data for _, data in sample.attachments])
                    for call in scan.call_args_list:
                        self.assertIn("--stdin", call.args[0])
                        self.assertTrue(call.kwargs["capture_output"])

    def test_non_clean_attachment_scan_fails_closed(self):
        with tempfile.TemporaryDirectory(prefix="embedded-corpus-") as temporary:
            source = Path(temporary) / "document.pdf"
            database = Path(temporary) / "signatures"
            database.mkdir()
            source.write_bytes(EMBEDDED_FILE_PDFS[0].content)
            with patch.object(inspector.subprocess, "run", return_value=
                              subprocess.CompletedProcess([], 1, b"stream: FOUND", b"")):
                with self.assertRaises(inspector.EmbeddedFileInspectionError) as context:
                    inspector.inspect_embedded_files(source, "/mock/clamscan", database)
            self.assertEqual(str(context.exception), inspector.BLOCK_MESSAGE)

    def test_clean_baselines_and_deployed_scan_gate_are_unchanged(self):
        self.assertTrue({s.identifier for s in EMBEDDED_FILE_PDFS}.isdisjoint(
            {s.identifier for s in REFERENCE_PDFS}))
        for reference in REFERENCE_PDFS:
            with self.subTest(reference=reference.identifier):
                self.assertNotIn(b"/EmbeddedFile", reference.content)
        scanner = (ROOT / "scan-and-open.py").read_text(encoding="utf-8")
        self.assertNotIn("embedded_file_corpus", scanner)
        self.assertIn("if not cached_clean(cache_id):", scanner)
        self.assertIn("remove_quarantine(path)", scanner)


if __name__ == "__main__":
    unittest.main()
