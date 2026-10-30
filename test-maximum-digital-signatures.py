#!/usr/bin/env python3
"""opener-0526: test real PDF signatures and Maximum's fail-closed handling."""
from datetime import datetime, timezone
from io import BytesIO
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.primitives.serialization import pkcs7
from pypdf import PdfReader, PdfWriter
from pypdf.generic import (
    ArrayObject, ByteStringObject, DecodedStreamObject, DictionaryObject,
    NameObject, NumberObject, TextStringObject,
)
import maximum_sanitized_copy as copies

ROOT = Path(__file__).resolve().parent
RESERVE = 4096
RANGE_MARKER = b"/ByteRange [ 0 9999999999 9999999999 9999999999 ]"


def signed_pdf(*, docmdp=False):
    """Generate genuine detached CMS without storing any private signing key."""
    writer = PdfWriter()
    page = writer.add_blank_page(width=260, height=180)
    artwork = DecodedStreamObject()
    artwork.set_data(b"q 0.82 0.12 0.17 rg 18 115 70 39 re f Q\n"
                     b"q 0.12 0.33 0.85 rg 164 28 72 47 re f Q\n")
    page[NameObject("/Contents")] = writer._add_object(artwork)
    signature = DictionaryObject({
        NameObject("/Type"): NameObject("/Sig"),
        NameObject("/Filter"): NameObject("/Adobe.PPKLite"),
        NameObject("/SubFilter"): NameObject("/adbe.pkcs7.detached"),
        NameObject("/ByteRange"): ArrayObject([
            NumberObject(0), NumberObject(9999999999),
            NumberObject(9999999999), NumberObject(9999999999),
        ]),
        NameObject("/Contents"): ByteStringObject(bytes(RESERVE)),
        NameObject("/Reason"): TextStringObject("SYNTHETIC-SIGNATURE"),
    })
    signature_ref = writer._add_object(signature)
    widget = DictionaryObject({
        NameObject("/Type"): NameObject("/Annot"),
        NameObject("/Subtype"): NameObject("/Widget"),
        NameObject("/FT"): NameObject("/Sig"),
        NameObject("/T"): TextStringObject("SYNTHETIC-SIGNER-FIELD"),
        NameObject("/V"): signature_ref,
        NameObject("/Rect"): ArrayObject([
            NumberObject(12), NumberObject(12),
            NumberObject(120), NumberObject(42),
        ]),
        NameObject("/P"): page.indirect_reference,
    })
    widget_ref = writer._add_object(widget)
    page[NameObject("/Annots")] = ArrayObject([widget_ref])
    writer._root_object[NameObject("/AcroForm")] = writer._add_object(
        DictionaryObject({
            NameObject("/Fields"): ArrayObject([widget_ref]),
            NameObject("/SigFlags"): NumberObject(3),
        })
    )
    if docmdp:
        writer._root_object[NameObject("/Perms")] = writer._add_object(
            DictionaryObject({NameObject("/DocMDP"): signature_ref})
        )
    output = BytesIO()
    writer.write(output)
    pdf = output.getvalue()
    placeholder = b"/Contents <" + b"00" * RESERVE + b">"
    assert pdf.count(placeholder) == pdf.count(RANGE_MARKER) == 1
    start = pdf.index(placeholder) + len(b"/Contents ")
    end = start + 2 * RESERVE + 2
    replacement = b"/ByteRange [ 0 " + b" ".join(
        f"{n:010d}".encode("ascii") for n in (
            start, end, len(pdf) - end
        )
    ) + b" ]"
    assert len(replacement) == len(RANGE_MARKER)
    pdf = pdf.replace(RANGE_MARKER, replacement, 1)
    covered = pdf[:start] + pdf[end:]

    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    name = x509.Name([x509.NameAttribute(
        x509.NameOID.COMMON_NAME, "Synthetic PDF test signer"
    )])
    certificate = (
        x509.CertificateBuilder().subject_name(name).issuer_name(name)
        .public_key(key.public_key()).serial_number(1)
        .not_valid_before(datetime(2020, 1, 1, tzinfo=timezone.utc))
        .not_valid_after(datetime(2035, 1, 1, tzinfo=timezone.utc))
        .sign(key, hashes.SHA256())
    )
    cms = (
        pkcs7.PKCS7SignatureBuilder().set_data(covered)
        .add_signer(certificate, key, hashes.SHA256())
        .sign(serialization.Encoding.DER, [
            pkcs7.PKCS7Options.Binary, pkcs7.PKCS7Options.DetachedSignature,
        ])
    )
    assert len(cms) <= RESERVE
    pdf = (pdf[:start + 1] +
           (cms + bytes(RESERVE - len(cms))).hex().encode("ascii") +
           pdf[end - 1:])
    assert pdf[:start] + pdf[end:] == covered
    return pdf, cms, covered


def cms_verifies(cms, content):
    """Verify the detached signature, not the untrusted certificate chain."""
    # This writes only public CMS and synthetic PDF bytes, never a key.
    with tempfile.TemporaryDirectory(prefix="pdf-fidelity-signature-") as temp:
        root = Path(temp)
        (root / "signature.der").write_bytes(cms)
        (root / "content.bin").write_bytes(content)
        result = subprocess.run([
            "openssl", "cms", "-verify", "-binary", "-inform", "DER",
            "-in", str(root / "signature.der"),
            "-content", str(root / "content.bin"), "-noverify",
            "-out", str(root / "verified.bin"),
        ], capture_output=True, timeout=15, check=False)
        return result.returncode == 0


class SignedPDFFidelityTests(unittest.TestCase):
    def test_real_signatures_and_byte_ranges_reject_tampering(self):
        for docmdp in (False, True):
            with self.subTest(docmdp=docmdp):
                pdf, cms, covered = signed_pdf(docmdp=docmdp)
                reader = PdfReader(BytesIO(pdf), strict=True)
                self.assertFalse(reader.is_encrypted)
                self.assertEqual(len(reader.pages), 1)
                root = reader.trailer["/Root"]
                self.assertEqual("/Perms" in root, docmdp)
                acroform = root["/AcroForm"].get_object()
                self.assertEqual(acroform["/SigFlags"], 3)
                self.assertEqual(len(acroform["/Fields"]), 1)
                field = acroform["/Fields"][0].get_object()
                self.assertEqual(field["/FT"], "/Sig")
                self.assertEqual(field["/Subtype"], "/Widget")
                self.assertEqual(len(reader.pages[0]["/Annots"]), 1)
                sig = field["/V"].get_object()
                self.assertEqual(sig["/Type"], "/Sig")
                self.assertEqual(sig["/SubFilter"], "/adbe.pkcs7.detached")
                start, count, end, tail = map(int, sig["/ByteRange"])
                self.assertEqual(start, 0)
                self.assertEqual(end + tail, len(pdf))
                self.assertEqual(pdf[count:count+1], b"<")
                self.assertEqual(pdf[end-1:end], b">")
                self.assertEqual(pdf[:count] + pdf[end:], covered)
                self.assertEqual(len(pkcs7.load_der_pkcs7_certificates(cms)), 1)
                self.assertTrue(cms_verifies(cms, covered))
                damaged = covered.replace(b"0.82 0.12", b"0.92 0.12", 1)
                self.assertNotEqual(damaged, covered)
                self.assertFalse(cms_verifies(cms, damaged))

    def test_signed_sources_never_render_or_offer_copies(self):
        for docmdp in (False, True):
            with self.subTest(docmdp=docmdp):
                source, _, _ = signed_pdf(docmdp=docmdp)
                with (
                    patch.object(copies, "_trusted_converter",
                                 return_value=Path("/synthetic-converter")),
                    patch.object(copies, "run_limited_converter") as renderer,
                ):
                    self.assertTrue(copies._unsupported_source_features(
                        PdfReader(BytesIO(source), strict=True)
                    ))
                    attempt = copies.attempt_sanitized_pdf_copy(source)
                    decision = copies.assess_sanitized_pdf_copy(source)
                    offer = copies.offer_sanitized_pdf_copy(source)
                renderer.assert_not_called()
                self.assertIsNone(offer)
                self.assertIsNone(attempt.offer)
                self.assertEqual(attempt.failure.kind,
                                 copies.SanitizerFailureKind.UNSUPPORTED_INPUT)
                self.assertEqual(attempt.failure.scan_verdict, "notAssessed")
                self.assertFalse(attempt.failure.permits_open)
                self.assertEqual(decision.action, "block")
                self.assertEqual(decision.blocked_reason,
                                 copies.SanitizationBlockReason.unsupportedFeature)
                self.assertFalse(decision.permits_open)
                self.assertFalse(decision.allow_fallback)
                self.assertFalse(decision.allow_clean_cache)
                self.assertTrue(decision.preserve_quarantine)
                self.assertTrue(decision.requires_separate_scan)
                for report in (attempt.failure.to_dict(), decision.to_dict()):
                    self.assertNotIn("SYNTHETIC-SIGNER", str(report))

    def test_unsigned_control_is_not_signature_blocked(self):
        writer = PdfWriter()
        writer.add_blank_page(width=260, height=180)
        output = BytesIO()
        writer.write(output)
        self.assertFalse(copies._unsupported_source_features(
            PdfReader(BytesIO(output.getvalue()), strict=True)
        ))

    def test_scanner_preferences_and_ci_stay_independent(self):
        workflow = (ROOT / ".github/workflows/ci.yml").read_text(
            encoding="utf-8"
        )
        scanner = (ROOT / "scan-and-open.py").read_text(encoding="utf-8")
        self.assertEqual(workflow.count(
            "python3 test-maximum-digital-signatures.py -v"), 2)
        self.assertIn("if not cached_clean(cache_id):", scanner)
        self.assertNotIn("test-maximum-digital-signatures.py", scanner)
        from protection_profiles import PROTECTION_PROFILES, ProtectionProfileID
        self.assertFalse(PROTECTION_PROFILES[ProtectionProfileID.MAXIMUM].selectable)
        offer = copies.SanitizedCopyOffer(b"synthetic-output", 1)
        self.assertFalse(offer.permits_open)
        self.assertTrue(offer.needs_separate_scan)


@unittest.skipUnless(sys.platform == "darwin", "CoreGraphics requires macOS")
class NativeSignedPDFFidelityTests(unittest.TestCase):
    def test_real_worker_output_cannot_keep_a_digital_signature(self):
        worker = ROOT / "maximum-sanitized-copy"
        self.assertTrue(worker.is_file(), "macOS CI must compile the real worker")
        for docmdp in (False, True):
            with self.subTest(docmdp=docmdp):
                source, _, _ = signed_pdf(docmdp=docmdp)
                result = subprocess.run(
                    [str(worker)], input=source, capture_output=True,
                    timeout=20, check=False,
                )
                if result.returncode != 0:
                    self.assertEqual(result.stdout, b"")
                    continue  # Native refusal is safe; no partial output.
                self.assertNotEqual(result.stdout, source)
                reader = PdfReader(BytesIO(result.stdout), strict=True)
                self.assertEqual(len(reader.pages), 1)
                self.assertEqual(float(reader.pages[0].mediabox.width), 260)
                self.assertEqual(float(reader.pages[0].mediabox.height), 180)
                self.assertNotIn("/AcroForm", reader.trailer["/Root"])
                self.assertNotIn("/Perms", reader.trailer["/Root"])
                self.assertNotIn("/Annots", reader.pages[0])
                for token in (b"/ByteRange", b"/SigFlags", b"/adbe.pkcs7.detached"):
                    self.assertNotIn(token, result.stdout)
                self.assertEqual((reader.pages[0].extract_text() or "").strip(), "")


if __name__ == "__main__":
    unittest.main()
