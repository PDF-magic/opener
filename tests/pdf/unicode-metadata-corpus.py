#!/usr/bin/env python3
"""opener-1043: actual valid PDFs with unusual Unicode Info/XMP metadata."""

from dataclasses import FrozenInstanceError
from hashlib import sha256
from io import BytesIO
from pathlib import Path
import unittest
from unittest.mock import patch

from pypdf import PdfReader

from pdf_declared_metadata import extract_pdf_declared_metadata
from pdf_structure_parser import parse_pdf_structure
from reference_pdf_collection import REFERENCE_PDFS
from unicode_metadata_corpus import UNICODE_METADATA_PDFS, _pdf_with_metadata


ROOT = Path(__file__).resolve().parents[2]

# Metadata keys exposed by the passive declared-metadata inspector.
INFO_KEYS = {"title", "author", "subject", "keywords"}


class UnicodeMetadataCorpusTests(unittest.TestCase):
    def test_real_distinct_reproducible_pdfs_with_valid_xrefs(self):
        self.assertEqual(len(UNICODE_METADATA_PDFS), 5)
        self.assertEqual(len({item.identifier for item in UNICODE_METADATA_PDFS}), 5)
        self.assertEqual(len({sha256(item.content).digest()
                              for item in UNICODE_METADATA_PDFS}), 5)
        for item in UNICODE_METADATA_PDFS:
            with self.subTest(pdf=item.identifier):
                self.assertTrue(item.content.startswith(b"%PDF-1."))
                self.assertTrue(item.content.rstrip().endswith(b"%%EOF"))
                self.assertLess(len(item.content), 16 * 1024)
                self.assertEqual(item.content.count(b"startxref"), 1)
                self.assertEqual(parse_pdf_structure(item.content).page_count, 1)
                self.assertEqual(len(PdfReader(BytesIO(item.content), strict=True).pages), 1)
                with self.assertRaises(FrozenInstanceError):
                    item.identifier = "modified"
                # No accidental metadata/raw-document disclosure in dataclass repr.
                self.assertNotIn("Καλημέρα", repr(item))

    def test_true_unicode_info_values_round_trip_without_normalization(self):
        for item in UNICODE_METADATA_PDFS:
            with self.subTest(pdf=item.identifier):
                reader = PdfReader(BytesIO(item.content), strict=True)
                info = {key[1:].lower(): str(value) for key, value in
                        reader.metadata.items() if key[1:].lower() in INFO_KEYS}
                self.assertEqual(info, {key.lower(): value for key, value in item.info})
                self.assertFalse(reader.is_encrypted)
        combined = UNICODE_METADATA_PDFS[0].content
        self.assertIn(b"\\376\\377", combined)  # Real PDF UTF-16BE BOM encoding.
        decomposed = dict(UNICODE_METADATA_PDFS[1].info)["author"]
        self.assertIn("e\u0301", decomposed)
        self.assertNotEqual(decomposed, "Café Ångström")
        self.assertIn("\u202e", dict(UNICODE_METADATA_PDFS[2].info)["title"])
        self.assertIn("\u200d", dict(UNICODE_METADATA_PDFS[2].info)["keywords"])

    def test_xmp_unicode_is_valid_raw_and_flate_rdf(self):
        for item in UNICODE_METADATA_PDFS[-2:]:
            with self.subTest(pdf=item.identifier):
                reader = PdfReader(BytesIO(item.content), strict=True)
                stream = reader.trailer["/Root"]["/Metadata"].get_object()
                self.assertEqual(stream["/Type"], "/Metadata")
                self.assertEqual(stream["/Subtype"], "/XML")
                self.assertIn(dict(item.xmp)["title"].encode("utf-8"),
                              stream.get_data())
                self.assertIn(dict(item.xmp)["author"].encode("utf-8"),
                              stream.get_data())
                self.assertEqual("/Filter" in stream,
                                 item.identifier == "xmp-compressed-combining")

    def test_passive_inspection_preserves_info_xmp_and_never_authorizes_open(self):
        for item in UNICODE_METADATA_PDFS:
            with self.subTest(pdf=item.identifier):
                with (patch("subprocess.Popen", side_effect=AssertionError("process")) as process,
                      patch("socket.create_connection", side_effect=AssertionError("network")) as network):
                    report = extract_pdf_declared_metadata(item.content)
                self.assertEqual(dict(report.info_fields),
                                 {"producer": "pypdf", **dict(item.info)})
                self.assertEqual(dict(report.xmp_fields), dict(item.xmp))
                self.assertEqual(report.has_xmp_stream, bool(item.xmp))
                self.assertIs(report.authorizes_open, False)
                self.assertIs(report.to_dict()["authorizesOpen"], False)
                for value in list(dict(item.info).values()) + list(dict(item.xmp).values()):
                    self.assertNotIn(value, repr(report))
                process.assert_not_called()
                network.assert_not_called()

    def test_fixture_isolation_from_scanner_and_existing_clean_baselines(self):
        self.assertEqual(len(REFERENCE_PDFS), 6)
        self.assertFalse({item.content for item in REFERENCE_PDFS}
                         & {item.content for item in UNICODE_METADATA_PDFS})
        for item in UNICODE_METADATA_PDFS:
            for forbidden in (b"/JavaScript", b"/Launch", b"/OpenAction",
                              b"/EmbeddedFiles", b"/AA "):
                self.assertNotIn(forbidden, item.content)
        scanner = (ROOT / "scan-and-open.py").read_text(encoding="utf-8")
        ci = (ROOT / ".github/workflows/ci.yml").read_text(encoding="utf-8")
        self.assertNotIn("unicode_metadata_corpus", scanner)
        self.assertIn("if not cached_clean(cache_id):", scanner)
        self.assertIn("PYTHONPATH=. python3 tests/pdf/unicode-metadata-corpus.py -v", ci)
        self.assertEqual(UNICODE_METADATA_PDFS[0].content,
                         _pdf_with_metadata({
                             "Title": "Καλημέρα 世界 مرحبا हिंदी 🚀",
                             "Author": "Zoë Nguyễn",
                             "Subject": "Українська עברית",
                         }))


if __name__ == "__main__":
    unittest.main()
