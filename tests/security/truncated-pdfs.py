#!/usr/bin/env python3
"""opener-1030: tracked truncated-PDF fixtures for the security test corpus.

The files contain deterministic, harmless prefixes of the existing clean
reference document. Testing passive structural failure does not activate an
unfinished protection profile or substitute for the live ClamAV scan gate.
"""

from hashlib import sha256
from pathlib import Path
import unittest

from pdf_malformed_structures import (
    BLOCK_MESSAGE,
    PDFMalformedStructureError,
    inspect_pdf_malformed_structures,
)
from pdf_structure_parser import (
    PDFStructureFailureCode,
    PDFStructureParseFailure,
    parse_pdf_structure_result,
)
from reference_pdf_collection import REFERENCE_PDFS


ROOT = Path(__file__).resolve().parents[2]
FIXTURE_DIR = ROOT / "tests/fixtures/pdf-security-corpus/truncated"
BASELINE = next(sample.content for sample in REFERENCE_PDFS
                if sample.identifier == "clean-basic")


def expected_truncations():
    """Use byte offsets in the good PDF, never synthesize malformed syntax."""
    stream_start = BASELINE.index(b"stream\n") + len(b"stream\n")
    stream_end = BASELINE.index(b"endstream", stream_start)
    xref_header = b"xref\n0 6\n0000000000 65535 f \n"
    xref_cut = BASELINE.index(xref_header) + len(xref_header) + 8
    eof_cut = BASELINE.index(b"%%EOF\n") + 3
    return {
        "truncated-stream.pdf": BASELINE[:(stream_start + stream_end) // 2],
        "truncated-xref.pdf": BASELINE[:xref_cut],
        "truncated-eof.pdf": BASELINE[:eof_cut],
    }


class TruncatedPDFCorpusTests(unittest.TestCase):
    def test_all_three_files_are_distinct_exact_prefixes_of_a_valid_reference(self):
        expected = expected_truncations()
        self.assertEqual(set(expected), {p.name for p in FIXTURE_DIR.glob("*.pdf")})
        self.assertTrue(BASELINE.startswith(b"%PDF-1.4\n"))
        self.assertTrue(BASELINE.endswith(b"%%EOF\n"))
        self.assertEqual(len({sha256(data).digest() for data in expected.values()}), 3)
        for name, prefix in expected.items():
            with self.subTest(fixture=name):
                path = FIXTURE_DIR / name
                self.assertTrue(path.is_file())
                actual = path.read_bytes()
                self.assertEqual(actual, prefix)
                self.assertLess(len(actual), len(BASELINE))
                self.assertTrue(BASELINE.startswith(actual))
                self.assertTrue(actual.startswith(b"%PDF-1.4\n"))
                self.assertNotIn(b"%%EOF\n", actual)

    def test_truncations_cut_three_distinct_pdf_structural_boundaries(self):
        samples = {name: (FIXTURE_DIR / name).read_bytes()
                   for name in expected_truncations()}
        self.assertIn(b"stream\n", samples["truncated-stream.pdf"])
        self.assertNotIn(b"endstream", samples["truncated-stream.pdf"])
        self.assertNotIn(b"xref\n", samples["truncated-stream.pdf"])
        self.assertTrue(samples["truncated-xref.pdf"].endswith(b"00000000"))
        self.assertNotIn(b"trailer\n", samples["truncated-xref.pdf"])
        self.assertTrue(samples["truncated-eof.pdf"].endswith(b"%%E"))
        self.assertIn(b"startxref\n", samples["truncated-eof.pdf"])

    def test_passive_integrity_checks_fail_closed_for_every_truncated_pdf(self):
        for name in expected_truncations():
            with self.subTest(fixture=name):
                damaged = (FIXTURE_DIR / name).read_bytes()
                with self.assertRaises(PDFMalformedStructureError) as raised:
                    inspect_pdf_malformed_structures(damaged)
                self.assertEqual(str(raised.exception), BLOCK_MESSAGE)
                result = parse_pdf_structure_result(damaged)
                self.assertIs(type(result), PDFStructureParseFailure)
                self.assertIs(result.code, PDFStructureFailureCode.invalidStructure)
                self.assertIs(result.to_dict()["authorizesOpen"], False)

    def test_ci_executes_corpus_regression(self):
        workflow = (ROOT / ".github/workflows/ci.yml").read_text(encoding="utf-8")
        self.assertIn("PYTHONPATH=. python3 tests/security/truncated-pdfs.py -v", workflow)


if __name__ == "__main__":
    unittest.main()
