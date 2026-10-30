#!/usr/bin/env python3
"""opener-0284: inspect indirect references and page-tree consistency."""

from dataclasses import FrozenInstanceError
from io import BytesIO
from pathlib import Path
import builtins
import unittest
from unittest.mock import patch

from pypdf import PdfWriter
from pypdf.generic import ArrayObject, IndirectObject, NameObject

from pdf_object_relationships import (
    MAX_RELATIONSHIP_OBJECTS, MAX_RELATIONSHIP_EDGES,
    PDFObjectRelationships, PDFObjectRelationshipError,
    inspect_pdf_object_relationships,
)
from reference_pdf_collection import REFERENCE_PDFS

ROOT = Path(__file__).resolve().parent


def generated_pdf(pages=1):
    writer = PdfWriter()
    for _ in range(pages):
        writer.add_blank_page(width=612, height=792)
    output = BytesIO()
    writer.write(output)
    return output.getvalue()


def check_error(test, content):
    with test.assertRaises(PDFObjectRelationshipError) as captured:
        inspect_pdf_object_relationships(content)
    test.assertIn("opening was stopped.", str(captured.exception))
    test.assertNotIn("/private/", str(captured.exception))


class ObjectRelationshipInspectionTests(unittest.TestCase):
    def test_shared_reference_collection_has_valid_relationships(self):
        self.assertEqual(len(REFERENCE_PDFS), 6)
        for sample in REFERENCE_PDFS:
            with self.subTest(pdf=sample.identifier):
                inspected = inspect_pdf_object_relationships(sample.content)
                self.assertIsInstance(inspected, PDFObjectRelationships)
                self.assertEqual(inspected.object_count, 5)
                self.assertEqual(inspected.page_count, 1)
                self.assertGreaterEqual(inspected.reference_count, 4)
                self.assertFalse(inspected.permits_open)
                with self.assertRaises(FrozenInstanceError):
                    inspected.page_count = 0

    def test_pypdf_generated_multi_page_relationships(self):
        for count in (1, 2, 5):
            with self.subTest(pages=count):
                inspected = inspect_pdf_object_relationships(generated_pdf(count))
                self.assertEqual(inspected.page_count, count)
                self.assertGreaterEqual(inspected.object_count, count + 2)
                self.assertFalse(inspected.permits_open)

    def test_embedded_strings_are_not_mistaken_for_indirect_references(self):
        # Complete valid reference corpus includes content streams and text.
        src = REFERENCE_PDFS[0].content
        self.assertIn(b"stream", src)
        inspected = inspect_pdf_object_relationships(src)
        self.assertEqual(inspected.page_count, 1)

    def test_unknown_indirect_reference_is_not_treated_as_resolved(self):
        writer = PdfWriter()
        page = writer.add_blank_page(width=612, height=792)
        page[NameObject("/InvalidLink")] = ArrayObject([IndirectObject(9999, 0, writer)])
        output = BytesIO()
        writer.write(output)
        check_error(self, output.getvalue())

    def test_parent_mismatch_blocks_relationship_verification(self):
        original = REFERENCE_PDFS[0].content
        self.assertIn(b"/Parent 2 0 R", original)
        changed = original.replace(b"/Parent 2 0 R", b"/Parent 1 0 R", 1)
        check_error(self, changed)

    def test_shared_page_child_is_rejected(self):
        original = REFERENCE_PDFS[0].content
        self.assertIn(b"/Kids [3 0 R]", original)
        # New bytes are longer, but xref offsets are deliberately not rewritten;
        # either a strict xref failure or duplicate child must be refused.
        changed = original.replace(b"/Kids [3 0 R]", b"/Kids [3 0 R 3 0 R]", 1)
        check_error(self, changed)

    def test_cyclic_page_tree_is_rejected_before_shared_parser_page_walk(self):
        src = REFERENCE_PDFS[0].content
        self.assertIn(b"/Kids [3 0 R]", src)
        cyclic = src.replace(b"/Kids [3 0 R]", b"/Kids [2 0 R]", 1)
        with patch("pdf_object_relationships.parse_pdf_structure") as parser:
            check_error(self, cyclic)
            parser.assert_not_called()

    def test_incorrect_page_count_is_rejected(self):
        src = REFERENCE_PDFS[0].content
        self.assertIn(b"/Count 1", src)
        check_error(self, src.replace(b"/Count 1", b"/Count 2", 1))

    def test_missing_objects_or_invalid_generations_block(self):
        src = REFERENCE_PDFS[0].content
        check_error(self, src.replace(b"/Contents 4 0 R", b"/Contents 9 0 R", 1))
        check_error(self, src.replace(b"/Contents 4 0 R", b"/Contents 4 1 R", 1))

    def test_encrypted_document_blocks_without_decryption(self):
        writer = PdfWriter()
        writer.add_blank_page(width=612, height=792)
        writer.encrypt("only-a-test-password")
        output = BytesIO()
        writer.write(output)
        check_error(self, output.getvalue())

    def test_unreadable_or_oversized_inputs_fail_closed(self):
        from pdf_structure_parser import MAX_STRUCTURE_INPUT_BYTES
        for invalid in (None, "PDF", 5, bytearray(REFERENCE_PDFS[0].content),
                        b"", b"%PDF-1.4\n", b"X" * (MAX_STRUCTURE_INPUT_BYTES + 1)):
            with self.subTest(kind=type(invalid).__name__):
                check_error(self, invalid)

    def test_unavailable_dependency_fails_closed(self):
        original = builtins.__import__

        def missing(name, *args, **kwargs):
            if name == "pypdf":
                raise ModuleNotFoundError("unavailable")
            return original(name, *args, **kwargs)

        with patch("builtins.__import__", side_effect=missing):
            check_error(self, REFERENCE_PDFS[0].content)

    def test_missing_or_corrupt_parser_errors_are_path_free(self):
        with patch("pdf_object_relationships.PdfReader", create=True):
            check_error(self, b"untrusted /private/secret.pdf")
        src = REFERENCE_PDFS[0].content
        with patch("pdf_object_relationships.parse_pdf_structure",
                   side_effect=ValueError("secret path /private/file.pdf")):
            check_error(self, src)

    def test_limits_and_inactive_integration_are_explicit(self):
        self.assertLessEqual(MAX_RELATIONSHIP_OBJECTS, 4096)
        self.assertLessEqual(MAX_RELATIONSHIP_EDGES, 65536)
        source = (ROOT / "pdf_object_relationships.py").read_text(encoding="utf-8")
        scanner = (ROOT / "scan-and-open.py").read_text(encoding="utf-8")
        resolver = (ROOT / "effective_protection_policy.py").read_text(encoding="utf-8")
        workflow = (ROOT / ".github/workflows/ci.yml").read_text(encoding="utf-8")
        self.assertNotIn("pdf_object_relationships", scanner)
        self.assertNotIn("pdf_object_relationships", resolver)
        self.assertIn("python3 scripts/run-test.py tests/pdf/object-relationships.py -v", workflow)
        self.assertIn("from pdf_structure_parser import", source)
        for forbidden in ("subprocess", "remove_quarantine(", "launch_clean_file(",
                          "UserDefaults", "os.system("):
            self.assertNotIn(forbidden, source)


if __name__ == "__main__":
    unittest.main()
