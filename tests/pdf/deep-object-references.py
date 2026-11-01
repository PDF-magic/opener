#!/usr/bin/env python3
"""opener-1033: an inert PDF corpus sample with deeply linked indirect objects."""

from io import BytesIO
from pathlib import Path
import unittest

from pypdf import PdfReader
from pypdf.generic import IndirectObject, NullObject

from pdf_object_relationships import (
    MAX_RELATIONSHIP_DEPTH, PDFObjectRelationshipError,
    inspect_pdf_object_relationships,
)
from pdf_structure_parser import (
    MAX_STRUCTURE_RECURSION_DEPTH, PDFStructure, parse_pdf_structure,
)
from reference_pdf_collection import (
    DEEP_OBJECT_REFERENCE_DEPTH, REFERENCE_PDFS, SECURITY_REFERENCE_PDFS,
    _deeply_nested_object_references_pdf,
)

ROOT = Path(__file__).resolve().parents[2]


class DeepObjectReferenceCorpusTests(unittest.TestCase):
    def test_complete_valid_pdf_has_96_distinct_indirect_reference_hops(self):
        self.assertGreater(DEEP_OBJECT_REFERENCE_DEPTH, MAX_RELATIONSHIP_DEPTH)
        self.assertGreater(DEEP_OBJECT_REFERENCE_DEPTH, MAX_STRUCTURE_RECURSION_DEPTH)
        self.assertEqual(len(SECURITY_REFERENCE_PDFS), 1)
        fixture = SECURITY_REFERENCE_PDFS[0]
        self.assertEqual(fixture.identifier, "deeply-nested-object-references")
        self.assertEqual(fixture.simulated_scanner_outcome, "clean")
        self.assertEqual(fixture.content, _deeply_nested_object_references_pdf())

        reader = PdfReader(BytesIO(fixture.content), strict=True)
        self.assertFalse(reader.is_encrypted)
        self.assertEqual(len(reader.pages), 1)
        self.assertEqual(reader.pages[0].extract_text().strip(),
                         "Nested references fixture")
        reference = reader.trailer["/Root"].raw_get("/DeepReference")
        visited = set()
        for index in range(DEEP_OBJECT_REFERENCE_DEPTH):
            with self.subTest(hop=index):
                self.assertIsInstance(reference, IndirectObject)
                self.assertEqual(reference.generation, 0)
                self.assertEqual(reference.idnum, index + 6)
                self.assertNotIn(reference.idnum, visited)
                visited.add(reference.idnum)
                obj = reference.get_object()
                self.assertEqual(obj["/Index"], index)
                reference = obj.raw_get("/Next")
        self.assertIsInstance(reference, NullObject)
        self.assertEqual(len(visited), DEEP_OBJECT_REFERENCE_DEPTH)

    def test_deep_links_pass_bounded_passive_structure_and_relationship_checks(self):
        content = SECURITY_REFERENCE_PDFS[0].content
        self.assertEqual(parse_pdf_structure(content), PDFStructure("1.4", 1))
        relationships = inspect_pdf_object_relationships(content)
        self.assertEqual(relationships.object_count,
                         5 + DEEP_OBJECT_REFERENCE_DEPTH)
        self.assertEqual(relationships.page_count, 1)
        self.assertGreaterEqual(relationships.reference_count,
                                4 + DEEP_OBJECT_REFERENCE_DEPTH)
        self.assertFalse(relationships.permits_open)

    def test_invalid_deep_link_is_not_treated_as_resolved(self):
        content = SECURITY_REFERENCE_PDFS[0].content
        self.assertIn(b"/Next 7 0 R", content)
        broken = content.replace(b"/Next 7 0 R", b"/Next 0 0 R", 1)
        self.assertEqual(len(broken), len(content))  # Keep xref offsets valid.
        with self.assertRaises(PDFObjectRelationshipError) as failure:
            inspect_pdf_object_relationships(broken)
        self.assertIn("opening was stopped.", str(failure.exception))

    def test_reference_corpus_remains_harmless_and_ci_runs_this_case(self):
        self.assertEqual(len(REFERENCE_PDFS), 6)
        content = SECURITY_REFERENCE_PDFS[0].content
        for active in (b"/JavaScript", b"/JS ", b"/Launch", b"/OpenAction",
                       b"/EmbeddedFiles", b"/AA "):
            with self.subTest(active=active):
                self.assertNotIn(active, content)
        workflow = (ROOT / ".github/workflows/ci.yml").read_text(encoding="utf-8")
        self.assertIn("PYTHONPATH=. python3 tests/pdf/deep-object-references.py -v",
                      workflow)
        scanner = (ROOT / "scan-and-open.py").read_text(encoding="utf-8")
        self.assertNotIn("SECURITY_REFERENCE_PDFS", scanner)


if __name__ == "__main__":
    unittest.main()
