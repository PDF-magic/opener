#!/usr/bin/env python3
"""opener-0424: verify direct and indirect PDF stream byte lengths."""

from dataclasses import FrozenInstanceError
from io import BytesIO
from pathlib import Path
from runpy import run_path
import unittest

from pypdf import PdfReader
from pdf_stream_lengths import PDFStreamLengthError, validate_pdf_stream_lengths
from pdf_structure_parser import PDFStructure, PDFStructureParseError, parse_pdf_structure
from reference_pdf_collection import REFERENCE_PDFS


ROOT = Path(__file__).resolve().parent


def pdf_with_stream(data=b"hello", *, declared=None, indirect=False,
                    unreferenced=False, newline=b"\n"):
  """Create a valid one-page PDF with exact classic cross-reference offsets."""
  length = len(data) if declared is None else declared
  bodies = [
    b"<< /Type /Catalog /Pages 2 0 R >>",
    b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
    b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 200 200] /Contents 4 0 R >>",
    b"<< /Length " + (b"5 0 R" if indirect else str(length).encode())
      + b" >>" + newline + b"stream" + newline + data
      + newline + b"endstream",
  ]
  if indirect:
    bodies.append(str(length).encode())
  if unreferenced:
    # The object is unreferenced by any page, but remains indexed and must
    # still be inspected. The malformed /Length is not allowed to hide.
    bodies.append(b"<< /Length 2 >>" + newline + b"stream" + newline
                  + b"unused" + newline + b"endstream")
  output = bytearray(b"%PDF-1.4" + newline)
  offsets = []
  for number, body in enumerate(bodies, 1):
    offsets.append(len(output))
    output.extend(f"{number} 0 obj".encode() + newline + body + newline
                  + b"endobj" + newline)
  startxref = len(output)
  output.extend(f"xref\n0 {len(bodies) + 1}\n0000000000 65535 f \n".encode())
  for offset in offsets:
    output.extend(f"{offset:010d} 00000 n \n".encode())
  output.extend(b"trailer\n<< /Size " + str(len(bodies) + 1).encode()
                + b" /Root 1 0 R >>\nstartxref\n"
                + str(startxref).encode() + b"\n%%EOF\n")
  return bytes(output)


class PDFStreamLengthTests(unittest.TestCase):
  def verify(self, contents, expected_streams):
    reader = PdfReader(BytesIO(contents), strict=True)
    self.assertEqual(validate_pdf_stream_lengths(contents, reader), expected_streams)
    self.assertEqual(parse_pdf_structure(contents), PDFStructure("1.4", 1))

  def rejected(self, contents):
    with self.assertRaises(PDFStructureParseError) as error:
      parse_pdf_structure(contents)
    self.assertEqual(str(error.exception),
                     "PDF structure could not be verified; opening was stopped.")

  def test_direct_indirect_zero_and_embedded_endstream_are_accepted(self):
    for payload, indirect, newline in (
      (b"hello", False, b"\n"),
      (b"", False, b"\r\n"),
      (b"hello\nendstream\nnot-the-end", True, b"\n"),
      (b"abc", True, b"\r\n"),
      (b"stream\n<< /Length 999 >>\nendstream", False, b"\n"),
    ):
      with self.subTest(length=len(payload), indirect=indirect, newline=newline):
        self.verify(pdf_with_stream(payload, indirect=indirect, newline=newline), 1)

  def test_existing_reference_collection_remains_accepted(self):
    for sample in REFERENCE_PDFS:
      with self.subTest(sample=sample.identifier):
        reader = PdfReader(BytesIO(sample.content), strict=True)
        self.assertGreaterEqual(validate_pdf_stream_lengths(sample.content, reader), 1)
        self.assertEqual(parse_pdf_structure(sample.content), PDFStructure("1.4", 1))

  def test_off_by_one_negative_and_invalid_indirect_lengths_rejected(self):
    payload = b"12345678"
    for length in (7, 9, 0, -1, 999999):
      for indirect in (False, True):
        with self.subTest(length=length, indirect=indirect):
          self.rejected(pdf_with_stream(payload, declared=length, indirect=indirect))

  def test_unreferenced_stream_cannot_hide_mismatched_length(self):
    self.rejected(pdf_with_stream(unreferenced=True))

  def test_missing_endstream_and_truncated_data_are_rejected(self):
    original = pdf_with_stream(b"hello")
    self.rejected(original.replace(b"\nendstream", b"\nendstreaX", 1))
    self.rejected(original.replace(b"stream\nhello\n", b"stream\nhell\n", 1))

  def test_pdf_15_xref_and_object_streams_have_matching_boundaries(self):
    make_fixture = run_path(
      str(ROOT / "test-pdf-cross-reference-parsing.py")
    )["make_xref_stream_pdf"]
    for objstream in (False, True):
      for compressed in (False, True):
        with self.subTest(object_stream=objstream, compressed=compressed):
          content = make_fixture(object_stream=objstream,
                                 compressed_xref=compressed)
          reader = PdfReader(BytesIO(content), strict=True)
          self.assertGreaterEqual(validate_pdf_stream_lengths(content, reader), 1)
          self.assertEqual(parse_pdf_structure(content), PDFStructure("1.5", 1))

  def test_invalid_types_and_no_parser_authorization(self):
    for invalid in (None, "", b"", bytearray(pdf_with_stream())):
      with self.subTest(kind=type(invalid).__name__):
        with self.assertRaises(PDFStreamLengthError):
          validate_pdf_stream_lengths(invalid, None)
    scanner = (ROOT / "scan-and-open.py").read_text(encoding="utf-8")
    module = (ROOT / "pdf_stream_lengths.py").read_text(encoding="utf-8")
    workflow = (ROOT / ".github/workflows/ci.yml").read_text(encoding="utf-8")
    self.assertNotIn("pdf_stream_lengths", scanner)
    self.assertNotIn("remove_quarantine(", module)
    self.assertNotIn("launch_clean_file(", module)
    self.assertNotIn("get_data(", module)
    self.assertIn("strict=True", (ROOT / "pdf_structure_parser.py").read_text())
    self.assertIn("python3 test-pdf-stream-lengths.py -v", workflow)
    self.assertIn("pip install --disable-pip-version-check -r requirements-enhanced-pdf.txt",
                  workflow)


if __name__ == "__main__":
  unittest.main()
