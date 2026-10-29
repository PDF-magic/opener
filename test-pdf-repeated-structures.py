#!/usr/bin/env python3
"""opener-0466: suspicious PDF repetition remains passive review evidence."""

from dataclasses import FrozenInstanceError
from io import BytesIO
from pathlib import Path
import unittest
from unittest.mock import patch

from pypdf import PdfWriter
from pypdf.generic import (
    ArrayObject, DecodedStreamObject, DictionaryObject, NameObject,
    NumberObject, TextStringObject, StreamObject,
)

import pdf_repeated_structures as stage
from pdf_repeated_structures import (
    DOMINANT_REPEATED_GROUP, MIN_REPEATED_GROUP, PDFRepeatedStructures,
    PDFRepeatedStructuresError, inspect_pdf_repeated_structures,
)
from reference_pdf_collection import REFERENCE_PDFS

ROOT = Path(__file__).resolve().parent
_ERROR = "PDF repeated structures could not be verified; opening was stopped."


def document(pages=1, repeated_dictionaries=0, repeated_arrays=0, streams=0):
    writer = PdfWriter()
    for _ in range(pages):
        writer.add_blank_page(width=200, height=200)
    for index in range(repeated_dictionaries):
        writer._add_object(DictionaryObject({
            NameObject("/Type"): NameObject("/CustomEntry"),
            NameObject("/Index"): NumberObject(index),
            NameObject("/Label"): TextStringObject(f"private-{index}"),
        }))
    for _ in range(repeated_arrays):
        writer._add_object(ArrayObject([
            NameObject("/CustomEntry"), NumberObject(1), TextStringObject("private"),
        ]))
    for _ in range(streams):
        stream = DecodedStreamObject()
        stream.set_data(b"PRIVATE STREAM CONTENT")
        writer._add_object(stream)
    output = BytesIO()
    writer.write(output)
    return output.getvalue()


class PDFRepeatedStructureTests(unittest.TestCase):
    def assert_rejected(self, contents):
        with self.assertRaises(PDFRepeatedStructuresError) as failure:
            inspect_pdf_repeated_structures(contents)
        self.assertEqual(str(failure.exception), _ERROR)
        self.assertNotIn("private", str(failure.exception).lower())
        self.assertIsNone(failure.exception.__cause__)

    def test_reference_documents_produce_bounded_non_authorizing_evidence(self):
        for sample in REFERENCE_PDFS:
            with self.subTest(pdf=sample.identifier):
                result = inspect_pdf_repeated_structures(sample.content)
                self.assertGreaterEqual(result.object_count, 1)
                self.assertLessEqual(result.object_count, stage.MAX_REPEATED_OBJECTS)
                self.assertFalse(result.suspicious_repetition)
                self.assertFalse(result.permits_open)
                self.assertFalse(result.to_dict()["authorizesOpen"])
                with self.assertRaises(FrozenInstanceError):
                    result.object_count = 0

    def test_ordinary_repeated_pages_do_not_count_as_suspicious_repetition(self):
        result = inspect_pdf_repeated_structures(document(pages=48))
        self.assertFalse(result.suspicious_repetition)
        self.assertLess(result.largest_repeated_group, MIN_REPEATED_GROUP)

    def test_repeated_non_page_dictionaries_with_varying_values_are_detected(self):
        result = inspect_pdf_repeated_structures(document(repeated_dictionaries=MIN_REPEATED_GROUP))
        self.assertEqual(result.largest_repeated_group, MIN_REPEATED_GROUP)
        self.assertEqual(result.repeated_object_count, MIN_REPEATED_GROUP)
        self.assertTrue(result.suspicious_repetition)
        self.assertNotIn("private", repr(result).lower())
        self.assertFalse(result.permits_open)

    def test_extreme_repetition_is_flagged_even_when_not_dominant(self):
        result = inspect_pdf_repeated_structures(document(
            pages=4, repeated_dictionaries=DOMINANT_REPEATED_GROUP,
        ))
        self.assertEqual(result.largest_repeated_group, DOMINANT_REPEATED_GROUP)
        self.assertTrue(result.suspicious_repetition)

    def test_small_repeated_groups_are_not_overstated(self):
        result = inspect_pdf_repeated_structures(document(repeated_dictionaries=8))
        self.assertEqual(result.largest_repeated_group, 8)
        self.assertFalse(result.suspicious_repetition)

    def test_arrays_are_structural_shapes_and_scalar_values_are_not_retained(self):
        result = inspect_pdf_repeated_structures(document(repeated_arrays=MIN_REPEATED_GROUP))
        self.assertEqual(result.largest_repeated_group, MIN_REPEATED_GROUP)
        self.assertTrue(result.suspicious_repetition)
        self.assertNotIn("private", repr(result.to_dict()).lower())

    def test_stream_payloads_are_not_decoded_or_counted_as_structures(self):
        content = document(streams=40)
        with patch.object(StreamObject, "get_data", side_effect=AssertionError("must not decode")):
            result = inspect_pdf_repeated_structures(content)
        self.assertFalse(result.suspicious_repetition)
        self.assertEqual(result.repeated_structure_groups, 0)

    def test_malformed_encrypted_and_invalid_inputs_fail_closed(self):
        for content in (None, "PDF", bytearray(b"%PDF-1.4"), b"secret private path", b""):
            with self.subTest(kind=type(content).__name__):
                self.assert_rejected(content)
        writer = PdfWriter()
        writer.add_blank_page(width=200, height=200)
        writer.encrypt("test-only")
        output = BytesIO()
        writer.write(output)
        self.assert_rejected(output.getvalue())

    def test_object_and_node_limits_fail_closed(self):
        with patch.object(stage, "MAX_REPEATED_OBJECTS", 2):
            self.assert_rejected(document(repeated_dictionaries=2))
        with patch.object(stage, "MAX_REPEATED_STRUCTURE_NODES", 2):
            self.assert_rejected(document(repeated_dictionaries=2))

    def test_result_contract_rejects_unbounded_or_authorizing_values(self):
        with self.assertRaises(ValueError):
            PDFRepeatedStructures(0, 0, 0, 0, 0, False)
        with self.assertRaises(ValueError):
            PDFRepeatedStructures(3, 3, 1, 2, 3, False)
        with self.assertRaises(ValueError):
            PDFRepeatedStructures(3, 3, 1, 3, 3, False, permits_open=True)

    def test_ci_coverage_and_scanner_isolation_are_explicit(self):
        scanner = (ROOT / "scan-and-open.py").read_text(encoding="utf-8")
        workflow = (ROOT / ".github/workflows/ci.yml").read_text(encoding="utf-8")
        module = (ROOT / "pdf_repeated_structures.py").read_text(encoding="utf-8")
        self.assertNotIn("pdf_repeated_structures", scanner)
        self.assertIn("python3 test-pdf-repeated-structures.py -v", workflow)
        for forbidden in ("subprocess.", "remove_quarantine(", "launch_clean_file(",
                          "UserDefaults", "os.system("):
            self.assertNotIn(forbidden, module)


if __name__ == "__main__":
    unittest.main()
