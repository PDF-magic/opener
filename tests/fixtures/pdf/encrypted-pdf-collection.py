"""Harmless, in-memory encrypted PDF documents for the security test corpus.

Only synthetic blank pages and public test passwords are used. Generating the
PDFs with the pinned test-only pypdf dependency avoids storing sensitive or
third-party encrypted documents. This corpus never decrypts or opens files.
"""

from dataclasses import dataclass
from io import BytesIO

from pypdf import PdfWriter


@dataclass(frozen=True)
class EncryptedReferencePDF:
    identifier: str
    content: bytes
    test_user_password: str
    key_bits: int


def _encrypted_pdf(identifier: str, user_password: str, owner_password: str,
                   *, use_128bit: bool = True) -> EncryptedReferencePDF:
    writer = PdfWriter()
    writer.add_blank_page(width=612, height=792)
    writer.encrypt(user_password=user_password, owner_password=owner_password,
                   use_128bit=use_128bit)
    output = BytesIO()
    writer.write(output)
    return EncryptedReferencePDF(identifier, output.getvalue(), user_password,
                                 128 if use_128bit else 40)


# Distinct cases cover password-required, owner-protected/empty-user-password,
# and legacy 40-bit encryption. All must remain blocked regardless of whether
# the fixture's deliberately public test password could decrypt the document.
ENCRYPTED_REFERENCE_PDFS = (
    _encrypted_pdf("user-and-owner-passwords", "corpus-user", "corpus-owner"),
    _encrypted_pdf("empty-user-password", "", "corpus-owner"),
    _encrypted_pdf("legacy-40-bit", "legacy-user", "legacy-owner",
                   use_128bit=False),
)
