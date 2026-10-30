#!/usr/bin/env python3
"""opener-0294: real PDF ambiguity and fail-closed regression coverage."""

from dataclasses import FrozenInstanceError
from io import BytesIO
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

from pypdf import PdfWriter

import pdf_structure_ambiguity as inspector


def pdf(objects=None):
    if objects is None:
        objects = (
            b"<< /Type /Catalog /Pages 2 0 R >>",
            b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
            b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 200 200] >>",
        )
    result = bytearray(b"%PDF-1.4\n")
    offsets = []
    for number, content in enumerate(objects, 1):
        offsets.append(len(result))
        result.extend(f"{number} 0 obj\n".encode() + content + b"\nendobj\n")
    xref = len(result)
    result.extend(f"xref\n0 {len(objects) + 1}\n0000000000 65535 f \n".encode())
    for offset in offsets:
        result.extend(f"{offset:010d} 00000 n \n".encode())
    result.extend(b"trailer\n<< /Size " + str(len(objects) + 1).encode()
                  + b" /Root 1 0 R >>\nstartxref\n"
                  + str(xref).encode() + b"\n%%EOF\n")
    return bytes(result)


class AmbiguityTests(unittest.TestCase):
    def test_valid_reference_and_generated_pdfs_provide_evidence_only(self):
        sample = pdf()
        result = inspector.inspect_pdf_structure_ambiguity(sample)
        self.assertEqual(result.inspected_objects, 3)
        self.assertFalse(result.ambiguous)
        self.assertFalse(result.permits_open)
        writer = PdfWriter()
        writer.add_blank_page(width=200, height=200)
        output = BytesIO()
        writer.write(output)
        self.assertGreater(inspector.inspect_pdf_structure_ambiguity(output.getvalue()).inspected_objects, 0)

    def test_duplicate_dictionary_keys_even_in_unused_objects_fail(self):
        duplicates = (
            b"<< /Type /Catalog /Pages 2 0 R /Pages 2 0 R >>",
            b"<< /First 1 /First 2 >>",
        )
        for duplicate in duplicates:
            with self.subTest(duplicate=duplicate):
                objects = list((b"<< /Type /Catalog /Pages 2 0 R >>",
                                b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
                                b"<< /Type /Page /Parent 2 0 R >>"))
                if b"/Type /Catalog" in duplicate:
                    objects[0] = duplicate
                else:
                    objects.append(duplicate)
                with self.assertRaises(inspector.PDFStructureAmbiguityError) as error:
                    inspector.inspect_pdf_structure_ambiguity(pdf(tuple(objects)))
                self.assertEqual(str(error.exception), inspector.BLOCK_MESSAGE)

    def test_conflicting_xref_pointer_and_shared_object_offset_fail(self):
        sample = pdf()
        original = f"{sample.index(b'2 0 obj'):010d} 00000 n".encode()
        replacement = f"{sample.index(b'1 0 obj'):010d} 00000 n".encode()
        changed = sample.replace(original, replacement, 1)
        self.assertNotEqual(changed, sample)
        with self.assertRaises(inspector.PDFStructureAmbiguityError):
            inspector.inspect_pdf_structure_ambiguity(changed)
        changed = sample.replace(b"startxref\n" + str(sample.index(b"xref\n")).encode(),
                                 b"startxref\n0")
        with self.assertRaises(inspector.PDFStructureAmbiguityError):
            inspector.inspect_pdf_structure_ambiguity(changed)

    def test_conflicting_tail_or_hidden_trailing_pdf_is_rejected(self):
        sample = pdf()
        for data in (sample + b"not whitespace", sample + b"%PDF-2.0\n",
                     sample.replace(b"%%EOF", b"%%EOZ"),
                     sample.replace(b"startxref", b"startxreff"),
                     sample.replace(b"%%EOF\n", b"%%EOF\nextra")):
            with self.subTest(size=len(data)):
                with self.assertRaises(inspector.PDFStructureAmbiguityError):
                    inspector.inspect_pdf_structure_ambiguity(data)

    def test_valid_incremental_revision_is_not_confused_with_conflict(self):
        original = pdf()
        prior = original.index(b"xref\n")
        # Older valid xref/EOF is not itself ambiguous. Revision inspection
        # belongs to opener-0291.
        modified = bytearray(original)
        updated = len(modified)
        modified.extend(b"1 0 obj\n<< /Type /Catalog /Pages 2 0 R >>\nendobj\n")
        newer = len(modified)
        modified.extend(f"xref\n1 1\n{updated:010d} 00000 n \n".encode())
        modified.extend(f"trailer\n<< /Size 4 /Root 1 0 R /Prev {prior} >>\n".encode())
        modified.extend(f"startxref\n{newer}\n%%EOF\n".encode())
        self.assertGreater(inspector.inspect_pdf_structure_ambiguity(bytes(modified)).inspected_objects, 0)

    def test_invalid_type_limits_encryption_and_missing_library_fail(self):
        for data in ("not bytes", b"", bytearray(pdf()), b"not a pdf",
                     pdf() + b" " * (inspector.MAX_PDF_BYTES + 1)):
            with self.subTest(kind=type(data).__name__):
                with self.assertRaises(inspector.PDFStructureAmbiguityError):
                    inspector.inspect_pdf_structure_ambiguity(data)
        writer = PdfWriter()
        writer.add_blank_page(width=200, height=200)
        writer.encrypt("pw")
        output = BytesIO()
        writer.write(output)
        with self.assertRaises(inspector.PDFStructureAmbiguityError):
            inspector.inspect_pdf_structure_ambiguity(output.getvalue())
        with patch.dict(sys.modules, {"pypdf": None}):
            with self.assertRaises(inspector.PDFStructureAmbiguityError):
                inspector.inspect_pdf_structure_ambiguity(pdf())

    def test_contract_immutable_and_never_approves_or_leaks(self):
        evidence = inspector.inspect_pdf_structure_ambiguity(pdf())
        with self.assertRaises(FrozenInstanceError):
            evidence.permits_open = True
        for kwargs in ({"inspected_objects": -1}, {"inspected_objects": 2, "permits_open": True},
                       {"inspected_objects": 2, "ambiguous": True}):
            with self.assertRaises(ValueError):
                inspector.PDFStructureAmbiguityInspection(**kwargs)
        error = inspector.PDFStructureAmbiguityError(inspector.BLOCK_MESSAGE)
        self.assertNotIn("/private", str(error))
        self.assertNotIn("secret", str(error))

    @unittest.skipUnless((Path(__file__).resolve().parent / "scan-and-open.py").is_file(),
                         "Requires repository checkout")
    def test_not_wired_into_deployed_gate_or_preferences(self):
        root = Path(__file__).resolve().parent
        scanner = (root / "scan-and-open.py").read_text()
        profiles = (root / "protection_profiles.py").read_text()
        self.assertNotIn("pdf_structure_ambiguity", scanner)
        self.assertIn("check_database()", scanner)
        self.assertIn("if not cached_clean(cache_id):", scanner)
        self.assertIn("remove_quarantine(path)", scanner)
        self.assertIn("selectable: bool = False", profiles)


if __name__ == "__main__":
    unittest.main()
