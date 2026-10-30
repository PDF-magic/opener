#!/usr/bin/env python3
"""opener-0290: verify bounded passive annotation inspection."""

from dataclasses import FrozenInstanceError
from io import BytesIO
from pathlib import Path
import os
import subprocess
import unittest
from unittest.mock import patch

from pypdf import PdfWriter
from pypdf.generic import (
    ArrayObject, DecodedStreamObject, DictionaryObject, FloatObject, NameObject, NumberObject,
    TextStringObject,
)
from pdf_annotations import (
    BLOCK_MESSAGE, MAX_PDF_BYTES, PDFAnnotationInspectionError,
    inspect_pdf_annotations,
)


def annotation(kind="Link", **fields):
    value = DictionaryObject({
        NameObject("/Type"): NameObject("/Annot"),
        NameObject("/Subtype"): NameObject("/" + kind),
        NameObject("/Rect"): ArrayObject([
            FloatObject(0), FloatObject(0), FloatObject(100), FloatObject(100),
        ]),
    })
    for key, content in fields.items():
        value[NameObject("/" + key)] = content
    return value


def pdf_with(*annotations, direct=False):
    writer = PdfWriter()
    page = writer.add_blank_page(width=500, height=500)
    if annotations:
        page[NameObject("/Annots")] = ArrayObject([
            obj if direct else writer._add_object(obj) for obj in annotations
        ])
    output = BytesIO()
    writer.write(output)
    return output.getvalue()


class PDFAnnotationTests(unittest.TestCase):
    def test_clean_reference_collection_is_inert_evidence_only(self):
        from reference_pdf_collection import REFERENCE_PDFS
        for pdf in REFERENCE_PDFS:
            with self.subTest(pdf=pdf.identifier):
                result = inspect_pdf_annotations(pdf.content)
                self.assertEqual(result.annotation_count, 0)
                self.assertFalse(result.needs_further_inspection)
                self.assertFalse(result.permits_open)
                with self.assertRaises(FrozenInstanceError):
                    result.permits_open = True

    def test_classifies_annotations_without_exposing_contents_or_executing(self):
        secret = "private secret annotation text and file path"
        launch = DictionaryObject({
            NameObject("/S"): NameObject("/Launch"),
            NameObject("/F"): TextStringObject("/private/secret")
        })
        js = DictionaryObject({
            NameObject("/S"): NameObject("/JavaScript"),
            NameObject("/JS"): TextStringObject("app.alert('secret')"),
        })
        appearance = DictionaryObject({
            NameObject("/N"): DictionaryObject({
                NameObject("/On"): DecodedStreamObject(),
            }),
        })
        with patch.object(os, "system") as shell, patch.object(subprocess, "run") as run:
            result = inspect_pdf_annotations(pdf_with(
                annotation("Link", Contents=TextStringObject(secret),
                           A=launch, Dest=NameObject("/private-destination")),
                annotation("Widget", AA=DictionaryObject({NameObject("/E"): js}),
                           AP=appearance),
                annotation("FileAttachment", FS=DictionaryObject({
                    NameObject("/F"): TextStringObject("secret-file.bin")
                })),
                annotation("RichMedia"),
            ))
        self.assertEqual(result.annotation_count, 4)
        self.assertEqual(result.annotation_kinds,
                         ("file_attachment", "link", "rich_media", "widget"))
        self.assertEqual((result.direct_action_count,
                          result.additional_action_annotations,
                          result.destination_count, result.active_annotation_count),
                         (1, 1, 1, 4))
        self.assertEqual(result.appearance_count, 1)
        self.assertTrue(result.needs_further_inspection)
        self.assertFalse(result.permits_open)
        self.assertNotIn(secret, repr(result))
        self.assertNotIn("private", repr(result))
        shell.assert_not_called()
        run.assert_not_called()

    def test_direct_annotations_and_indirect_arrays(self):
        result = inspect_pdf_annotations(pdf_with(annotation("Text"), direct=True))
        self.assertEqual(result.annotation_kinds, ("text",))
        self.assertEqual(result.active_annotation_count, 0)

    def test_malformed_annotations_fail_closed(self):
        invalid = [
            annotation("UnknownSubtype"),
            annotation("Link", A=NameObject("/Launch")),
            annotation("Link", AA=DictionaryObject()),
            annotation("Widget", AA=DictionaryObject({
                NameObject("/E"): DictionaryObject()
            })),
            annotation("Link", Dest=NumberObject(17)),
            annotation("Link", AP=DictionaryObject({NameObject("/N"): NumberObject(3)})),
            annotation("Link", F=TextStringObject("bad flags")),
            annotation("FileAttachment"),
        ]
        missing_rect = annotation("Text")
        del missing_rect["/Rect"]
        invalid.append(missing_rect)
        for entry in invalid:
            with self.subTest(entry=repr(entry)[:90]):
                with self.assertRaises(PDFAnnotationInspectionError) as error:
                    inspect_pdf_annotations(pdf_with(entry))
                self.assertEqual(str(error.exception), BLOCK_MESSAGE)

    def test_duplicate_annotations_fail_closed(self):
        writer = PdfWriter()
        page = writer.add_blank_page(width=100, height=100)
        ref = writer._add_object(annotation("Text"))
        page[NameObject("/Annots")] = ArrayObject([ref, ref])
        output = BytesIO()
        writer.write(output)
        with self.assertRaises(PDFAnnotationInspectionError):
            inspect_pdf_annotations(output.getvalue())

    def test_annotation_count_limit_fails_closed(self):
        from pdf_annotations import MAX_ANNOTATIONS
        writer = PdfWriter()
        page = writer.add_blank_page(width=100, height=100)
        entry = annotation("Text")
        page[NameObject("/Annots")] = ArrayObject([entry] * (MAX_ANNOTATIONS + 1))
        output = BytesIO()
        writer.write(output)
        with self.assertRaises(PDFAnnotationInspectionError):
            inspect_pdf_annotations(output.getvalue())

    def test_invalid_document_size_encryption_and_truncation_fail_closed(self):
        writer = PdfWriter()
        writer.add_blank_page(width=100, height=100)
        writer.encrypt("private")
        output = BytesIO()
        writer.write(output)
        samples = (b"", b"garbage", "not bytes", b"%PDF-1.7\ntruncated",
                   pdf_with(annotation("Text"))[:-15], output.getvalue(),
                   b"%PDF-1.7" + b"x" * MAX_PDF_BYTES + b"%%EOF")
        for sample in samples:
            with self.subTest(size=len(sample)):
                with self.assertRaises(PDFAnnotationInspectionError) as error:
                    inspect_pdf_annotations(sample)
                self.assertEqual(str(error.exception), BLOCK_MESSAGE)

    def test_no_scanner_policy_or_preference_change(self):
        root = Path(__file__).resolve().parents[2]
        source = (root / "scan-and-open.py").read_text()
        self.assertNotIn("pdf_annotations", source)
        self.assertIn("if not cached_clean(cache_id):", source)
        from protection_policy_definitions import PROTECTION_POLICIES, ProtectionProfileID
        self.assertFalse(PROTECTION_POLICIES[ProtectionProfileID.ENHANCED].selectable)


if __name__ == "__main__":
    unittest.main()
