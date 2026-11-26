"""Synthetic, cryptographically signed PDF security corpus (opener-1040).

Signing keys are ephemeral and never written to disk. This test-only corpus
must not be used as a trust store, signer validation or opening authorization.
"""

from dataclasses import dataclass
from datetime import datetime, timezone
from functools import lru_cache
from io import BytesIO

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.primitives.serialization import pkcs7
from pypdf import PdfWriter
from pypdf.generic import (
    ArrayObject, ByteStringObject, DictionaryObject, NameObject, NumberObject,
    TextStringObject,
)


_RESERVED_SIGNATURE_BYTES = 4096
_RANGE_MARKER = b"/ByteRange [ 0 9999999999 9999999999 9999999999 ]"


@dataclass(frozen=True)
class SignedPDF:
    identifier: str
    content: bytes
    signature_der: bytes
    signed_bytes: bytes
    docmdp: bool


def _build_signed_pdf(*, docmdp: bool) -> SignedPDF:
    writer = PdfWriter()
    page = writer.add_blank_page(width=260, height=180)
    signature = DictionaryObject({
        NameObject("/Type"): NameObject("/Sig"),
        NameObject("/Filter"): NameObject("/Adobe.PPKLite"),
        NameObject("/SubFilter"): NameObject("/adbe.pkcs7.detached"),
        NameObject("/ByteRange"): ArrayObject([
            NumberObject(0), NumberObject(9999999999),
            NumberObject(9999999999), NumberObject(9999999999),
        ]),
        NameObject("/Contents"): ByteStringObject(bytes(_RESERVED_SIGNATURE_BYTES)),
        NameObject("/Reason"): TextStringObject("Synthetic test signature"),
    })
    if docmdp:
        signature[NameObject("/Reference")] = ArrayObject([
            DictionaryObject({
                NameObject("/Type"): NameObject("/SigRef"),
                NameObject("/TransformMethod"): NameObject("/DocMDP"),
                NameObject("/TransformParams"): DictionaryObject({
                    NameObject("/Type"): NameObject("/TransformParams"),
                    NameObject("/P"): NumberObject(2),
                    NameObject("/V"): NameObject("/1.2"),
                }),
            }),
        ])
    signature_ref = writer._add_object(signature)
    widget = writer._add_object(DictionaryObject({
        NameObject("/Type"): NameObject("/Annot"),
        NameObject("/Subtype"): NameObject("/Widget"),
        NameObject("/FT"): NameObject("/Sig"),
        NameObject("/T"): TextStringObject("Synthetic test signer"),
        NameObject("/V"): signature_ref,
        NameObject("/Rect"): ArrayObject([
            NumberObject(12), NumberObject(12), NumberObject(130), NumberObject(40),
        ]),
        NameObject("/P"): page.indirect_reference,
    }))
    page[NameObject("/Annots")] = ArrayObject([widget])
    writer._root_object[NameObject("/AcroForm")] = writer._add_object(
        DictionaryObject({
            NameObject("/Fields"): ArrayObject([widget]),
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
    placeholder = b"/Contents <" + b"00" * _RESERVED_SIGNATURE_BYTES + b">"
    if pdf.count(placeholder) != 1 or pdf.count(_RANGE_MARKER) != 1:
        raise ValueError("Unexpected PDF signature serialization")
    start = pdf.index(placeholder) + len(b"/Contents ")
    end = start + 2 * _RESERVED_SIGNATURE_BYTES + 2
    range_value = b"/ByteRange [ 0 " + b" ".join(
        f"{value:010d}".encode("ascii")
        for value in (start, end, len(pdf) - end)
    ) + b" ]"
    if len(range_value) != len(_RANGE_MARKER):
        raise ValueError("PDF ByteRange reservation overflow")
    pdf = pdf.replace(_RANGE_MARKER, range_value, 1)
    covered = pdf[:start] + pdf[end:]

    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    name = x509.Name([x509.NameAttribute(
        x509.NameOID.COMMON_NAME, "Untrusted synthetic test signer"
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
    if len(cms) > _RESERVED_SIGNATURE_BYTES:
        raise ValueError("Synthetic CMS exceeds reserved PDF signature space")
    pdf = (pdf[:start + 1]
           + (cms + bytes(_RESERVED_SIGNATURE_BYTES - len(cms))).hex().encode("ascii")
           + pdf[end - 1:])
    if pdf[:start] + pdf[end:] != covered:
        raise ValueError("Signed PDF byte ranges changed")
    return SignedPDF(
        "certification-docmdp" if docmdp else "approval-signature",
        pdf, cms, covered, docmdp,
    )


@lru_cache(maxsize=1)
def signed_pdf_corpus() -> tuple[SignedPDF, ...]:
    """Two complete one-page PDFs with genuine detached CMS signatures."""
    return (_build_signed_pdf(docmdp=False), _build_signed_pdf(docmdp=True))
