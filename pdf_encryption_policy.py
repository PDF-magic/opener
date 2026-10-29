"""Read-only encryption policy evidence for the optional PDF parsing foundation.

All encrypted PDFs are blocked while required contents cannot be inspected,
including files whose user password is blank or whose owner password is set.
This inspector NEVER attempts decryption, accepts passwords, opens PDF files,
or grants a malware-clean result. The installed ClamAV gate remains unchanged.
"""

from dataclasses import dataclass
from enum import Enum
from io import BytesIO
import re

from unsupported_pdf_features import (
    ENCRYPTED_RESPONSE,
    INCOMPLETE_RESPONSE,
    UnsupportedPDFResponse,
)

MAX_ENCRYPTION_INSPECTION_BYTES = 16 * 1024 * 1024
_HEADER = re.compile(rb"\A%PDF-(?:1\.[0-7]|2\.0)[\r\n]")
_FAILURE = "PDF encryption could not be verified; opening was stopped."


class PDFEncryptionInspectionError(RuntimeError):
    """Uninspectable content: always incomplete, never clean or openable."""

    response = INCOMPLETE_RESPONSE


class PDFEncryptionStatus(str, Enum):
    NOT_ENCRYPTED = "notEncrypted"
    ENCRYPTED = "encrypted"


@dataclass(frozen=True)
class PDFEncryptionInspection:
    """Evidence only; even an unencrypted file has not passed safety checks."""

    status: PDFEncryptionStatus
    response: UnsupportedPDFResponse | None
    permits_open: bool = False

    def __post_init__(self) -> None:
        if (type(self.status) is not PDFEncryptionStatus or
                self.response is not (
                    ENCRYPTED_RESPONSE if self.status is PDFEncryptionStatus.ENCRYPTED
                    else None
                ) or self.permits_open is not False):
            raise ValueError("Encryption inspection cannot authorize an opening")


_UNENCRYPTED = PDFEncryptionInspection(PDFEncryptionStatus.NOT_ENCRYPTED, None)
_ENCRYPTED = PDFEncryptionInspection(PDFEncryptionStatus.ENCRYPTED, ENCRYPTED_RESPONSE)


def inspect_pdf_encryption(contents: bytes) -> PDFEncryptionInspection:
    """Check a strict PDF's encryption state without trying any credentials.

    All PDF encryption is conservatively uninspectable in this foundation,
    irrespective of whether the document needs a nonempty user password,
    offers an empty password, or has a separate owner password. Detect via the
    parsed trailer, never a raw ``/Encrypt`` substring. Malformed/unsupported
    structures fail closed rather than being mistaken for unencrypted PDFs.
    """
    if (type(contents) is not bytes or not 0 < len(contents) <= MAX_ENCRYPTION_INSPECTION_BYTES
            or _HEADER.match(contents[:9]) is None
            or b"%%EOF" not in contents[-1024:]):
        raise PDFEncryptionInspectionError(_FAILURE)
    try:
        from pypdf import PdfReader
        reader = PdfReader(BytesIO(contents), strict=True)
        encrypted = reader.is_encrypted
        if type(encrypted) is not bool:
            raise PDFEncryptionInspectionError(_FAILURE)
    except Exception:
        # Parser errors can include document-controlled strings or file names.
        raise PDFEncryptionInspectionError(_FAILURE) from None
    return _ENCRYPTED if encrypted else _UNENCRYPTED
