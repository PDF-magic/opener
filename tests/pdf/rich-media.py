#!/usr/bin/env python3
"""opener-0447: rich-media content is detected without decoding or playback."""

from dataclasses import FrozenInstanceError
from io import BytesIO
from pathlib import Path
import os
import socket
import subprocess
import unittest
from unittest.mock import patch

from pypdf import PdfWriter
from pypdf.generic import (
  ArrayObject, DictionaryObject, FloatObject, NameObject, TextStringObject,
)
from pdf_rich_media import (
  BLOCK_MESSAGE, MAX_PDF_BYTES, MAX_MEDIA_ENTRIES, PDFRichMediaInspectionError,
  inspect_pdf_rich_media,
)
from reference_pdf_collection import REFERENCE_PDFS


ROOT = Path(__file__).resolve().parents[2]


def create_pdf(*, annotation=True, orphan=False, assets=True,
               configurations=True, invalid=None):
  writer = PdfWriter()
  page = writer.add_blank_page(width=200, height=200)
  content = DictionaryObject()
  if assets:
    spec = writer._add_object(DictionaryObject({
      NameObject("/Type"): NameObject("/Filespec"),
      NameObject("/F"): TextStringObject("private-video.mp4"),
    }))
    content[NameObject("/Assets")] = writer._add_object(DictionaryObject({
      NameObject("/Names"): ArrayObject([
        TextStringObject("private-video.mp4"), spec,
      ]),
    }))
  if configurations:
    config = writer._add_object(DictionaryObject({
      NameObject("/Type"): NameObject("/RichMediaConfiguration"),
      NameObject("/Subtype"): NameObject("/Video"),
    }))
    content[NameObject("/Configurations")] = ArrayObject([config])
  content_ref = writer._add_object(content)
  if annotation:
    item = DictionaryObject({
      NameObject("/Type"): NameObject("/Annot"),
      NameObject("/Subtype"): NameObject("/RichMedia"),
      NameObject("/Rect"): ArrayObject([
        FloatObject(0), FloatObject(0), FloatObject(20), FloatObject(20)
      ]),
      NameObject("/RichMediaContent"): content_ref,
      NameObject("/RichMediaSettings"): DictionaryObject({
        NameObject("/Activation"): DictionaryObject({
          NameObject("/Condition"): NameObject("/XA")
        }),
      }),
    })
    if invalid == "content_type":
      item[NameObject("/RichMediaContent")] = TextStringObject("invalid")
    elif invalid == "missing_content":
      del item[NameObject("/RichMediaContent")]
    page[NameObject("/Annots")] = ArrayObject([writer._add_object(item)])
  elif orphan:
    writer._root_object[NameObject("/CustomRichMediaHolder")] = DictionaryObject({
      NameObject("/RichMediaContent"): content_ref,
    })
  output = BytesIO()
  writer.write(output)
  return output.getvalue()


class PDFRichMediaTests(unittest.TestCase):
  def test_reference_collection_has_no_rich_media(self):
    for item in REFERENCE_PDFS:
      with self.subTest(name=item.identifier):
        report = inspect_pdf_rich_media(item.content)
        self.assertFalse(report.has_rich_media)
        self.assertEqual((report.annotation_count, report.content_count,
                          report.configuration_count, report.asset_reference_count),
                         (0, 0, 0, 0))
        self.assertFalse(report.permits_open)

  def test_annotation_referenced_content_configuration_and_assets(self):
    with (patch.object(socket, "getaddrinfo") as dns,
          patch.object(os, "system") as shell,
          patch.object(subprocess, "run") as process):
      report = inspect_pdf_rich_media(create_pdf())
    self.assertEqual((report.annotation_count, report.content_count,
                      report.configuration_count, report.asset_reference_count),
                     (1, 1, 1, 1))
    self.assertTrue(report.has_rich_media)
    self.assertFalse(report.permits_open)
    self.assertNotIn("private-video.mp4", repr(report))
    dns.assert_not_called()
    shell.assert_not_called()
    process.assert_not_called()
    with self.assertRaises(FrozenInstanceError):
      report.asset_reference_count = 100

  def test_non_annotation_content_and_configs_remain_detectable(self):
    for options in ({"annotation": False, "orphan": True},
                    {"annotation": False, "orphan": False}):
      with self.subTest(options=options):
        report = inspect_pdf_rich_media(create_pdf(**options))
        self.assertEqual(report.annotation_count, 0)
        self.assertGreaterEqual(report.content_count, 0)
        self.assertEqual(report.configuration_count, 1)
        self.assertEqual(report.asset_reference_count,
                         1 if options["orphan"] else 0)

  def test_content_is_not_required_to_contain_optional_assets(self):
    report = inspect_pdf_rich_media(create_pdf(assets=False, configurations=False))
    self.assertEqual(report.annotation_count, 1)
    self.assertEqual(report.content_count, 1)
    self.assertEqual(report.asset_reference_count, 0)

  def test_missing_or_wrong_type_rich_media_content_fails_closed(self):
    for invalid in ("content_type", "missing_content"):
      with self.subTest(invalid=invalid):
        with self.assertRaises(PDFRichMediaInspectionError) as caught:
          inspect_pdf_rich_media(create_pdf(invalid=invalid))
        self.assertEqual(str(caught.exception), BLOCK_MESSAGE)

  def test_bad_assets_name_tree_structure_fails_closed(self):
    writer = PdfWriter()
    writer.add_blank_page(width=100, height=100)
    invalid_tree = writer._add_object(DictionaryObject({
      NameObject("/Names"): ArrayObject([TextStringObject("dangling-name")])
    }))
    content = writer._add_object(DictionaryObject({
      NameObject("/Assets"): invalid_tree
    }))
    writer._root_object[NameObject("/RichMediaContent")] = content
    out = BytesIO()
    writer.write(out)
    with self.assertRaises(PDFRichMediaInspectionError):
      inspect_pdf_rich_media(out.getvalue())

  def test_oversized_malformed_and_encrypted_inputs_fail_closed(self):
    cases = (b"", "not bytes", bytearray(create_pdf()), b"garbage",
             create_pdf()[:-15], b"%PDF-1.4\n" + b"z" * MAX_PDF_BYTES)
    for data in cases:
      with self.subTest(kind=type(data).__name__):
        with self.assertRaises(PDFRichMediaInspectionError) as caught:
          inspect_pdf_rich_media(data)
        self.assertEqual(str(caught.exception), BLOCK_MESSAGE)
    writer = PdfWriter()
    writer.add_blank_page(width=100, height=100)
    writer.encrypt("secret")
    out = BytesIO()
    writer.write(out)
    with self.assertRaises(PDFRichMediaInspectionError):
      inspect_pdf_rich_media(out.getvalue())

  def test_metadata_validation_and_scanner_isolation(self):
    from pdf_rich_media import PDFRichMediaInspection
    for invalid in (-1, True, MAX_MEDIA_ENTRIES + 1):
      with self.subTest(value=invalid), self.assertRaises(ValueError):
        PDFRichMediaInspection(0, 0, 0, invalid)
    scan = (ROOT / "scan-and-open.py").read_text(encoding="utf-8")
    workflow = (ROOT / ".github/workflows/ci.yml").read_text(encoding="utf-8")
    module = (ROOT / "pdf_rich_media.py").read_text(encoding="utf-8")
    self.assertNotIn("pdf_rich_media", scan)
    self.assertIn("if not cached_clean(cache_id):", scan)
    self.assertIn("python3 tests/pdf/rich-media.py -v", workflow)
    self.assertNotIn("get_data(", module)
    self.assertNotIn("remove_quarantine(", module)
    self.assertNotIn("launch_clean_file(", module)
    from protection_policy_definitions import PROTECTION_POLICIES, ProtectionProfileID
    self.assertFalse(PROTECTION_POLICIES[ProtectionProfileID.ENHANCED].selectable)


if __name__ == "__main__":
  unittest.main()
