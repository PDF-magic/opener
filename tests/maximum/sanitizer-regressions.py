#!/usr/bin/env python3
"""opener-1094: regress the optional sanitizer's full output trust boundary.

The converter is synthetic. All PDF reconstruction, passive-content checks and
final structural validation are real; no scanner, browser or user files run.
"""

from io import BytesIO
from pathlib import Path
import subprocess
import unittest
from unittest.mock import patch
import zlib

from PIL import Image
from pypdf import PdfReader, PdfWriter
from pypdf.generic import (
    DictionaryObject, NameObject, NumberObject, StreamObject, TextStringObject,
)

import maximum_sanitized_copy as sanitizer
from maximum_sanitized_structure import verify_sanitized_pdf_structure


MARKER = "PRIVATE-SANITIZER-REGRESSION"


def serialize(writer):
    buffer = BytesIO()
    writer.write(buffer)
    return buffer.getvalue()


def taint(writer):
    writer._root_object[NameObject("/OpenAction")] = writer._add_object(
        DictionaryObject({
            NameObject("/S"): NameObject("/JavaScript"),
            NameObject("/JS"): TextStringObject(MARKER),
        })
    )
    writer.add_attachment("private-attachment.bin", b"MZ" + MARKER.encode())
    writer.add_metadata({"/Title": MARKER})


def source_pdf(*, unsupported=False):
    writer = PdfWriter()
    writer.add_blank_page(width=160, height=200)
    taint(writer)
    if unsupported:
        writer._root_object[NameObject("/Collection")] = DictionaryObject()
    return serialize(writer)


def raster_pdf(*, width=160, extra_image=False):
    writer = PdfWriter()
    page = writer.add_blank_page(width=width, height=200)
    image = StreamObject()
    image._data = zlib.compress(Image.new("RGB", (4, 4), (20, 80, 160)).tobytes())
    image.update({
        NameObject("/Type"): NameObject("/XObject"),
        NameObject("/Subtype"): NameObject("/Image"),
        NameObject("/Width"): NumberObject(4),
        NameObject("/Height"): NumberObject(4),
        NameObject("/ColorSpace"): NameObject("/DeviceRGB"),
        NameObject("/BitsPerComponent"): NumberObject(8),
        NameObject("/Filter"): NameObject("/FlateDecode"),
    })
    ref = writer._add_object(image)
    objects = DictionaryObject({NameObject("/Im0"): ref})
    if extra_image:
        objects[NameObject("/Im1")] = ref
    page[NameObject("/Resources")] = DictionaryObject({
        NameObject("/XObject"): objects,
    })
    content = StreamObject()
    content._data = b"q 160 0 0 200 0 0 cm /Im0 Do Q\n"
    page[NameObject("/Contents")] = writer._add_object(content)
    taint(writer)
    page[NameObject("/AA")] = DictionaryObject({
        NameObject("/O"): DictionaryObject({
            NameObject("/S"): NameObject("/Launch"),
        }),
    })
    return serialize(writer)


class SanitizerRegressionTests(unittest.TestCase):
    def setUp(self):
        self.source = source_pdf()

    def attempt(self, output, *, on_activity=None):
        with patch.object(
            sanitizer, "_trusted_converter", return_value=Path("/usr/bin/true")
        ), patch.object(
            sanitizer, "run_limited_converter",
            return_value=subprocess.CompletedProcess([], 0, output),
        ) as run:
            attempt = sanitizer.attempt_sanitized_pdf_copy(
                self.source, on_activity=on_activity,
            )
        run.assert_called_once()
        return attempt

    def test_active_payload_is_removed_before_independently_verified_offer(self):
        candidate = raster_pdf()
        self.assertIn("/OpenAction", PdfReader(BytesIO(self.source)).trailer["/Root"])
        tainted = PdfReader(BytesIO(candidate), strict=True)
        self.assertIn("/OpenAction", tainted.trailer["/Root"])
        self.assertIn("/Names", tainted.trailer["/Root"])
        self.assertIn("/AA", tainted.pages[0])
        events = []
        result = self.attempt(candidate, on_activity=events.append)
        self.assertIsNone(result.failure)
        self.assertIsNotNone(result.offer)
        offer = result.offer
        self.assertNotEqual(offer.pdf_bytes, candidate)
        self.assertNotEqual(offer.pdf_bytes, self.source)
        self.assertEqual(offer.page_count, 1)
        self.assertIs(offer.permits_open, False)
        self.assertIs(offer.needs_separate_scan, True)
        self.assertIs(result.permits_open, False)
        self.assertEqual([event["phase"] for event in events], ["sanitizing", "idle"])
        self.assertTrue(all(event["authorizesOpen"] is False for event in events))

        structure = verify_sanitized_pdf_structure(offer.pdf_bytes, 1)
        self.assertEqual(structure.page_count, 1)
        self.assertIs(structure.permits_open, False)
        output = PdfReader(BytesIO(offer.pdf_bytes), strict=True)
        self.assertEqual(set(output.trailer["/Root"]), {"/Type", "/Pages"})
        self.assertNotIn("/Info", output.trailer)
        self.assertNotIn("/ID", output.trailer)
        self.assertNotIn("/Annots", output.pages[0])
        self.assertNotIn("/AA", output.pages[0])
        self.assertEqual(len(output.pages[0].images), 1)
        self.assertNotIn(MARKER.encode(), offer.pdf_bytes)
        self.assertNotIn(b"private-attachment.bin", offer.pdf_bytes)

    def test_poisoned_or_invalid_converter_output_fails_closed(self):
        cases = {
            "mismatched geometry": raster_pdf(width=161),
            "multiple image XObjects": raster_pdf(extra_image=True),
            "truncated result": raster_pdf()[:96],
            "non-PDF": b"invalid converter output",
        }
        for label, output in cases.items():
            with self.subTest(label=label):
                outcome = self.attempt(output)
                self.assertIsNone(outcome.offer)
                self.assertEqual(
                    outcome.failure.kind, sanitizer.SanitizerFailureKind.INVALID_OUTPUT,
                )
                report = outcome.failure.to_dict()
                self.assertEqual(report["scanVerdict"], "notAssessed")
                self.assertIs(report["permitsOpen"], False)
                self.assertIs(report["sanitizationComplete"], False)
                self.assertNotIn(MARKER, str(report))
                with patch.object(
                    sanitizer, "_trusted_converter", return_value=Path("/usr/bin/true")
                ), patch.object(
                    sanitizer, "run_limited_converter",
                    return_value=subprocess.CompletedProcess([], 0, output),
                ):
                    decision = sanitizer.assess_sanitized_pdf_copy(self.source)
                self.assertEqual(decision.action, "block")
                self.assertIs(decision.permits_open, False)
                self.assertIs(decision.allow_fallback, False)
                self.assertIs(decision.allow_clean_cache, False)
                self.assertIs(decision.preserve_quarantine, True)

    def test_unsupported_source_is_rejected_before_worker_launch(self):
        with patch.object(
            sanitizer, "_trusted_converter", return_value=Path("/usr/bin/true")
        ), patch.object(sanitizer, "run_limited_converter") as run:
            outcome = sanitizer.attempt_sanitized_pdf_copy(
                source_pdf(unsupported=True),
            )
        run.assert_not_called()
        self.assertIsNone(outcome.offer)
        self.assertEqual(
            outcome.failure.kind, sanitizer.SanitizerFailureKind.UNSUPPORTED_INPUT,
        )
        self.assertEqual(outcome.failure.to_dict()["scanVerdict"], "notAssessed")


if __name__ == "__main__":
    unittest.main()
