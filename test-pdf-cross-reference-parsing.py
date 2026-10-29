#!/usr/bin/env python3
"""opener-0416: exercise all three PDF cross-reference representations."""

from io import BytesIO
from pathlib import Path
import unittest
import zlib

from pypdf import PdfReader
from pypdf.generic import IndirectObject

from pdf_structure_parser import PDFStructure, PDFStructureParseError, parse_pdf_structure
from reference_pdf_collection import REFERENCE_PDFS


ROOT = Path(__file__).resolve().parent


def make_xref_stream_pdf(*, object_stream=False, compressed_xref=False,
                         bad_xref_width=False, bad_object_count=False):
  """Build a one-page PDF 1.5 using correct byte offsets and indirect refs.

  The object-stream case stores the page dictionary as compressed object 3;
  there is no standalone 3 0 obj to fall back to. No document is written to
  disk, fetched, rendered, or opened by the installed scanner.
  """
  document = bytearray(b"%PDF-1.5\n%\xe2\xe3\xcf\xd3\n")
  offsets = {}

  def write_object(number, value):
    offsets[number] = len(document)
    document.extend(f"{number} 0 obj\n".encode("ascii"))
    document.extend(value)
    document.extend(b"\nendobj\n")

  write_object(1, b"<< /Type /Catalog /Pages 2 0 R >>")
  write_object(2, b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>")

  if object_stream:
    objects = b"3 0 << /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] >>"
    count = 0 if bad_object_count else 1
    dictionary = (
      f"<< /Type /ObjStm /N {count} /First 4 /Length {len(objects)} >>\n"
    ).encode("ascii")
    write_object(4, dictionary + b"stream\n" + objects + b"\nendstream")
    xref_number = 5
  else:
    write_object(3, b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] >>")
    xref_number = 4

  offsets[xref_number] = len(document)

  def entry(number):
    if number == 0:
      return bytes((0,)) + (0).to_bytes(4, "big") + (65535).to_bytes(2, "big")
    if number == 3 and object_stream:
      return bytes((2,)) + (4).to_bytes(4, "big") + (0).to_bytes(2, "big")
    return bytes((1,)) + offsets[number].to_bytes(4, "big") + (0).to_bytes(2, "big")

  entries = b"".join(entry(i) for i in range(xref_number + 1))
  width = b"[1 4 0]" if bad_xref_width else b"[1 4 2]"
  if compressed_xref:
    entries = zlib.compress(entries)
  filter_spec = b"/Filter /FlateDecode " if compressed_xref else b""
  dictionary = (
    b"<< /Type /XRef /Size " + str(xref_number + 1).encode("ascii")
    + b" /Root 1 0 R /W " + width
    + b" /Index [0 " + str(xref_number + 1).encode("ascii") + b"] "
    + filter_spec + b"/Length " + str(len(entries)).encode("ascii") + b" >>\n"
  )
  write_object(xref_number, dictionary + b"stream\n" + entries + b"\nendstream")
  document.extend(b"startxref\n" + str(offsets[xref_number]).encode("ascii") + b"\n%%EOF\n")
  return bytes(document)


class PDFCrossReferenceParsingTests(unittest.TestCase):
  def test_traditional_cross_reference_tables_resolve_pages(self):
    for sample in REFERENCE_PDFS:
      with self.subTest(pdf=sample.identifier):
        self.assertIn(b"\nxref\n", sample.content)
        reader = PdfReader(BytesIO(sample.content), strict=True)
        self.assertTrue(reader.xref)
        self.assertEqual(reader.xref_objStm, {})
        self.assertEqual(parse_pdf_structure(sample.content), PDFStructure("1.4", 1))

  def test_cross_reference_streams_resolve_pages(self):
    for compressed in (False, True):
      with self.subTest(flate=compressed):
        contents = make_xref_stream_pdf(compressed_xref=compressed)
        self.assertIn(b"/Type /XRef", contents)
        reader = PdfReader(BytesIO(contents), strict=True)
        self.assertEqual(reader.xref_objStm, {})
        self.assertEqual(len(reader.pages), 1)
        self.assertEqual(parse_pdf_structure(contents), PDFStructure("1.5", 1))

  def test_object_stream_page_is_really_resolved_from_compressed_entry(self):
    for compressed in (False, True):
      with self.subTest(flate=compressed):
        contents = make_xref_stream_pdf(
          object_stream=True, compressed_xref=compressed
        )
        self.assertNotIn(b"3 0 obj\n", contents)
        reader = PdfReader(BytesIO(contents), strict=True)
        self.assertEqual(reader.xref_objStm[3], (4, 0))
        page = reader.get_object(IndirectObject(3, 0, reader))
        self.assertEqual(page["/Type"], "/Page")
        self.assertEqual(parse_pdf_structure(contents), PDFStructure("1.5", 1))

  def test_broken_xref_and_object_stream_indexes_fail_closed(self):
    cases = (
      make_xref_stream_pdf(bad_xref_width=True),
      make_xref_stream_pdf(object_stream=True, bad_object_count=True),
    )
    for contents in cases:
      with self.subTest(object_stream=b"/ObjStm" in contents):
        with self.assertRaises(PDFStructureParseError) as failure:
          parse_pdf_structure(contents)
        self.assertEqual(
          str(failure.exception),
          "PDF structure could not be verified; opening was stopped.",
        )

  def test_parser_is_passive_and_ci_executes_real_fixture_tests(self):
    scanner = (ROOT / "scan-and-open.py").read_text(encoding="utf-8")
    workflow = (ROOT / ".github/workflows/ci.yml").read_text(encoding="utf-8")
    module = (ROOT / "pdf_structure_parser.py").read_text(encoding="utf-8")
    relationships = (ROOT / "pdf_object_relationships.py").read_text(
      encoding="utf-8"
    )
    self.assertNotIn("pdf_structure_parser", scanner)
    self.assertNotIn("pdf_object_relationships", scanner)
    self.assertIn("reader.xref_objStm", relationships)
    self.assertIn("raise PDFObjectRelationshipError(_UNSUPPORTED)", relationships)
    self.assertIn("strict=True", module)
    self.assertIn("MAX_STRUCTURE_INPUT_BYTES", module)
    self.assertIn("python3 test-pdf-cross-reference-parsing.py -v", workflow)
    self.assertIn("pip install --disable-pip-version-check -r requirements-enhanced-pdf.txt", workflow)


if __name__ == "__main__":
  unittest.main()
