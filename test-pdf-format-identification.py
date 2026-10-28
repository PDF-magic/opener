#!/usr/bin/env python3
"""opener-0282: identify PDF format from local bytes, never a file extension."""

from dataclasses import FrozenInstanceError
from pathlib import Path
import os
import tempfile
import unittest
from unittest.mock import patch

from pdf_format_identification import (
    NOT_PDF, UNDETERMINED, PDFFormatStatus, identify_pdf_format,
    identify_pdf_header,
)
from reference_pdf_collection import REFERENCE_PDFS

ROOT = Path(__file__).resolve().parent


class PDFFormatIdentificationTests(unittest.TestCase):
    def test_reference_corpus_is_identified_without_trusting_extension(self):
        with tempfile.TemporaryDirectory(prefix="pdf-format-") as directory:
            for sample in REFERENCE_PDFS:
                for suffix in (".pdf", ".bin", ""):
                    with self.subTest(sample=sample.identifier, suffix=suffix):
                        path = Path(directory) / (sample.identifier + suffix)
                        path.write_bytes(sample.content)
                        result = identify_pdf_format(path)
                        self.assertIs(result.status, PDFFormatStatus.PDF_HEADER)
                        self.assertEqual(result.version, "1.4")
                        self.assertEqual(result.media_type, "application/pdf")
                        self.assertFalse(result.permits_open)

    def test_supported_pdf_versions_require_a_complete_first_line(self):
        for version in [*(f"1.{minor}" for minor in range(8)), "2.0"]:
            for newline in (b"\n", b"\r"):
                with self.subTest(version=version, newline=newline):
                    result = identify_pdf_header(b"%PDF-" + version.encode() + newline)
                    self.assertIs(result.status, PDFFormatStatus.PDF_HEADER)
                    self.assertEqual(result.version, version)
                    self.assertFalse(result.permits_open)

    def test_extensions_and_embedded_markers_cannot_spoof_pdf_bytes(self):
        with tempfile.TemporaryDirectory(prefix="pdf-spoof-") as directory:
            for index, body in enumerate((
                b"PK\x03\x04" + b"%PDF-1.7\n", b"\x89PNG\r\n\x1a\n",
                b"\xff\xd8\xff\xe0", b"MZ" + b"%PDF-1.7\n",
                b"junk\n%PDF-1.4\n", b"%PDF-1.4 " + b"%PDF-2.0\n",
                b"this is a plain text document", b"\xef\xbb\xbf%PDF-1.7\n",
            )):
                with self.subTest(index=index):
                    path = Path(directory) / f"spoof-{index}.PDF"
                    path.write_bytes(body)
                    self.assertIs(identify_pdf_format(path), NOT_PDF if not body.startswith(b"%PDF-") else UNDETERMINED)

    def test_missing_or_malformed_headers_do_not_claim_a_pdf(self):
        for data in (b"", b"%", b"%PDF", b"%PDF-", b"%PDF-1.4",
                     b"%PDF-1.8\n", b"%PDF-2.1\n", b"%PDF-3.0\n",
                     b"%PDF-1.4X", b"%PDF-1.x\n", b"%PDF-\xff.4\n"):
            with self.subTest(data=data):
                self.assertIs(identify_pdf_header(data), UNDETERMINED)
        self.assertIs(identify_pdf_header(b"hello"), NOT_PDF)
        with self.assertRaises(TypeError):
            identify_pdf_header("%PDF-1.7\n")

    def test_unreadable_and_non_regular_entries_fail_without_opening_or_writing(self):
        with tempfile.TemporaryDirectory(prefix="pdf-format-path-") as directory:
            root = Path(directory)
            source = root / "original.pdf"
            source.write_bytes(b"%PDF-2.0\n" + b"test")
            symlink = root / "alias.pdf"
            symlink.symlink_to(source)
            folder = root / "folder.pdf"
            folder.mkdir()
            fifo = root / "pipe.pdf"
            os.mkfifo(fifo)
            for path in (root / "missing.pdf", symlink, folder, fifo):
                with self.subTest(path=path.name):
                    self.assertIs(identify_pdf_format(path), UNDETERMINED)
            self.assertIs(identify_pdf_format(None), UNDETERMINED)
            self.assertEqual(source.read_bytes(), b"%PDF-2.0\ntest")
            with patch("pdf_format_identification.os.open", side_effect=PermissionError("/private/secret.pdf")):
                result = identify_pdf_format(source)
                self.assertIs(result, UNDETERMINED)
                self.assertNotIn("secret", repr(result))

    def test_only_header_bytes_are_read_even_for_large_files(self):
        with tempfile.TemporaryDirectory(prefix="pdf-format-bound-") as directory:
            source = Path(directory) / "large.bin"
            with source.open("wb") as stream:
                stream.write(b"%PDF-1.7\n")
                stream.truncate(64 * 1024 * 1024)
            real_fdopen = os.fdopen
            reads = []

            class BoundedReader:
                def __init__(self, source):
                    self.source = source
                def __enter__(self):
                    self.source.__enter__()
                    return self
                def __exit__(self, *args):
                    return self.source.__exit__(*args)
                def read(self, size=-1):
                    reads.append(size)
                    return self.source.read(size)
                def fileno(self):
                    return self.source.fileno()

            with patch("pdf_format_identification.os.fdopen",
                       side_effect=lambda *args, **kwargs: BoundedReader(real_fdopen(*args, **kwargs))):
                result = identify_pdf_format(source)
            self.assertEqual(reads, [9])
            self.assertEqual(result.version, "1.7")
            self.assertEqual(source.stat().st_size, 64 * 1024 * 1024)

    def test_format_evidence_is_immutable_and_does_not_activate_enhanced(self):
        result = identify_pdf_header(b"%PDF-2.0\n")
        with self.assertRaises(FrozenInstanceError):
            result.version = "1.0"
        self.assertFalse(result.permits_open)
        scanner = (ROOT / "scan-and-open.py").read_text(encoding="utf-8")
        self.assertNotIn("pdf_format_identification", scanner)
        policy = (ROOT / "protection_profiles.py").read_text(encoding="utf-8")
        self.assertIn("selectable: bool = False", policy)
        workflow = (ROOT / ".github/workflows/ci.yml").read_text(encoding="utf-8")
        self.assertIn("python3 test-pdf-format-identification.py -v", workflow)


if __name__ == "__main__":
    unittest.main()
