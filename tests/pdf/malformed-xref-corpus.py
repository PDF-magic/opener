#!/usr/bin/env python3
"""opener-1031: exercise deterministic malformed cross-reference table corpus."""

from hashlib import sha256
from pathlib import Path
import re
import unittest

from malformed_xref_pdf_collection import MALFORMED_XREF_PDFS
from pdf_malformed_structures import (
    BLOCK_MESSAGE,
    PDFMalformedStructureError,
    inspect_pdf_malformed_structures,
)
from reference_pdf_collection import REFERENCE_PDFS


ROOT = Path(__file__).resolve().parents[2]


class MalformedXRefCorpusTests(unittest.TestCase):
    def test_clean_reference_is_a_valid_control(self):
        clean = next(sample.content for sample in REFERENCE_PDFS
                     if sample.identifier == "clean-basic")
        report = inspect_pdf_malformed_structures(clean)
        self.assertEqual(report.page_count, 1)
        self.assertFalse(report.permits_open)
        self.assertFalse(report.malformed)

    def test_corpus_is_distinct_and_only_changes_classic_xref_tables(self):
        clean = next(sample.content for sample in REFERENCE_PDFS
                     if sample.identifier == "clean-basic")
        prefix = clean.split(b"xref\n0 6\n", 1)[0]
        expected_names = {
            "xref-out-of-bounds-offset",
            "xref-conflicting-object-offsets",
            "xref-generation-mismatch",
            "xref-overdeclared-subsection",
            "xref-nonnumeric-subsection",
            "xref-truncated-entry-table",
        }
        self.assertEqual({sample.identifier for sample in MALFORMED_XREF_PDFS},
                         expected_names)
        self.assertEqual(len(MALFORMED_XREF_PDFS), len(expected_names))
        fingerprints = {sha256(clean).digest()}
        for sample in MALFORMED_XREF_PDFS:
            with self.subTest(sample=sample.identifier):
                contents = sample.content
                self.assertIs(type(contents), bytes)
                self.assertTrue(contents.startswith(prefix + b"xref\n"))
                self.assertIn(b"trailer\n<< /Size 6 /Root 1 0 R >>", contents)
                self.assertTrue(contents.endswith(b"%%EOF\n"))
                match = re.search(rb"startxref\n(\d+)\n%%EOF\n\Z", contents)
                self.assertIsNotNone(match)
                self.assertEqual(int(match.group(1)), len(prefix))
                fingerprints.add(sha256(contents).digest())
        self.assertEqual(len(fingerprints), len(MALFORMED_XREF_PDFS) + 1)

    def test_structurally_invalid_tables_fail_closed(self):
        # These failures are not repaired by pypdf's strict reader.
        rejected = {
            "xref-generation-mismatch",
            "xref-overdeclared-subsection",
            "xref-nonnumeric-subsection",
            "xref-truncated-entry-table",
        }
        for sample in MALFORMED_XREF_PDFS:
            if sample.identifier not in rejected:
                continue
            with self.subTest(sample=sample.identifier):
                with self.assertRaises(PDFMalformedStructureError) as raised:
                    inspect_pdf_malformed_structures(sample.content)
                self.assertEqual(str(raised.exception), BLOCK_MESSAGE)

    def test_parser_recovery_never_authorizes_an_open(self):
        # pypdf may repair malformed offset rows even in strict mode. These
        # samples remain in the corpus to document that limitation; without
        # a dedicated original-xref preflight, parser success is NOT proof of
        # physical table integrity and never authorizes an opening.
        recovered = {
            "xref-out-of-bounds-offset",
            "xref-conflicting-object-offsets",
        }
        for sample in MALFORMED_XREF_PDFS:
            if sample.identifier not in recovered:
                continue
            with self.subTest(sample=sample.identifier):
                original = sample.content
                try:
                    report = inspect_pdf_malformed_structures(original)
                except PDFMalformedStructureError as error:
                    self.assertEqual(str(error), BLOCK_MESSAGE)
                else:
                    self.assertFalse(report.permits_open)
                self.assertIs(sample.content, original)

    def test_scanner_policy_preferences_and_ci_wiring_are_unchanged(self):
        scanner = (ROOT / "scan-and-open.py").read_text(encoding="utf-8")
        workflow = (ROOT / ".github/workflows/ci.yml").read_text(
            encoding="utf-8"
        )
        self.assertNotIn("malformed_xref_pdf_collection", scanner)
        self.assertNotIn("pdf_malformed_structures", scanner)
        self.assertIn("if not cached_clean(cache_id):", scanner)
        self.assertIn("verify_file_integrity", scanner)
        self.assertIn("python3 tests/pdf/malformed-xref-corpus.py -v", workflow)
        from protection_policy_definitions import PROTECTION_POLICIES, ProtectionProfileID
        self.assertFalse(PROTECTION_POLICIES[ProtectionProfileID.ENHANCED].selectable)


if __name__ == "__main__":
    unittest.main()
