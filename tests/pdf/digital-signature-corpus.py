#!/usr/bin/env python3
"""opener-1040: real signed PDF samples remain passive test inputs."""

from dataclasses import FrozenInstanceError
from io import BytesIO
from pathlib import Path
import subprocess
import tempfile
import unittest

from cryptography.hazmat.primitives.serialization import pkcs7
from pypdf import PdfReader

from digital_signature_corpus import signed_pdf_corpus
from pdf_document_permissions import inspect_pdf_document_permissions
from pdf_structure_parser import PDFStructure, parse_pdf_structure
from reference_pdf_collection import REFERENCE_PDFS

ROOT = Path(__file__).resolve().parents[2]


def _verify_detached_signature(der: bytes, content: bytes) -> bool:
    """Verify only CMS integrity; the synthetic self-signed cert is untrusted."""
    with tempfile.TemporaryDirectory(prefix="pdf-signed-corpus-") as temp:
        root = Path(temp)
        (root / "signature.der").write_bytes(der)
        (root / "covered.bin").write_bytes(content)
        result = subprocess.run([
            "openssl", "cms", "-verify", "-binary", "-inform", "DER",
            "-in", str(root / "signature.der"),
            "-content", str(root / "covered.bin"), "-noverify",
            "-out", str(root / "checked.bin"),
        ], capture_output=True, timeout=15, check=False)
        return result.returncode == 0


class DigitalSignatureCorpusTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.corpus = signed_pdf_corpus()

    def test_two_distinct_complete_signed_documents(self):
        self.assertEqual(
            {item.identifier for item in self.corpus},
            {"approval-signature", "certification-docmdp"},
        )
        self.assertEqual(len({item.content for item in self.corpus}), 2)
        self.assertIs(self.corpus, signed_pdf_corpus())
        for item in self.corpus:
            with self.subTest(sample=item.identifier):
                self.assertLess(len(item.content), 32 * 1024)
                self.assertTrue(item.content.startswith(b"%PDF-"))
                self.assertTrue(item.content.rstrip().endswith(b"%%EOF"))
                self.assertEqual(parse_pdf_structure(item.content), PDFStructure("1.3", 1))
                reader = PdfReader(BytesIO(item.content), strict=True)
                self.assertFalse(reader.is_encrypted)
                self.assertEqual(len(reader.pages), 1)
                root = reader.trailer["/Root"]
                self.assertEqual("/Perms" in root, item.docmdp)
                form = root["/AcroForm"].get_object()
                self.assertEqual(form["/SigFlags"], 3)
                self.assertEqual(len(form["/Fields"]), 1)
                field = form["/Fields"][0].get_object()
                self.assertEqual(field["/FT"], "/Sig")
                self.assertEqual(field["/Subtype"], "/Widget")
                self.assertEqual(len(reader.pages[0]["/Annots"]), 1)
                signature = field["/V"].get_object()
                self.assertEqual(signature["/Type"], "/Sig")
                self.assertEqual(signature["/SubFilter"], "/adbe.pkcs7.detached")
                if item.docmdp:
                    self.assertEqual(root["/Perms"]["/DocMDP"].get_object(), signature)
                with self.assertRaises(FrozenInstanceError):
                    item.docmdp = False

    def test_exact_signed_ranges_and_tampering(self):
        for item in self.corpus:
            with self.subTest(sample=item.identifier):
                reader = PdfReader(BytesIO(item.content), strict=True)
                form = reader.trailer["/Root"]["/AcroForm"]
                signature = form["/Fields"][0].get_object()["/V"].get_object()
                start, count, end, tail = map(int, signature["/ByteRange"])
                self.assertEqual(start, 0)
                self.assertEqual(end + tail, len(item.content))
                self.assertEqual(item.content[count:count + 1], b"<")
                self.assertEqual(item.content[end - 1:end], b">")
                self.assertEqual(item.content[:count] + item.content[end:], item.signed_bytes)
                self.assertEqual(len(pkcs7.load_der_pkcs7_certificates(item.signature_der)), 1)
                self.assertTrue(_verify_detached_signature(item.signature_der, item.signed_bytes))
                tampered = bytearray(item.signed_bytes)
                tampered[20] ^= 1
                self.assertFalse(_verify_detached_signature(item.signature_der, bytes(tampered)))

    def test_passive_inspection_never_treats_signature_as_trust(self):
        for item in self.corpus:
            with self.subTest(sample=item.identifier):
                report = inspect_pdf_document_permissions(item.content)
                self.assertFalse(report.is_encrypted)
                self.assertEqual(report.catalog_declarations,
                                 ("doc_mdp",) if item.docmdp else ())
                self.assertEqual(report.declared_doc_mdp_level, 2 if item.docmdp else None)
                self.assertFalse(report.signature_verified)
                self.assertFalse(report.authorizes_open)

    def test_existing_baselines_and_live_scanner_are_unchanged(self):
        self.assertEqual(len(REFERENCE_PDFS), 6)
        self.assertFalse(
            {item.identifier for item in self.corpus}
            & {item.identifier for item in REFERENCE_PDFS}
        )
        scanner = (ROOT / "scan-and-open.py").read_text(encoding="utf-8")
        self.assertNotIn("digital_signature_corpus", scanner)
        self.assertIn("if not cached_clean(cache_id):", scanner)
        workflow = (ROOT / ".github/workflows/pdf-digital-signature-corpus.yml").read_text()
        self.assertIn("python3 tests/pdf/digital-signature-corpus.py -v", workflow)


if __name__ == "__main__":
    unittest.main()
