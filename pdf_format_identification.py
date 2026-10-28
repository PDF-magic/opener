"""Bounded, read-only PDF header identification for planned Enhanced inspection.

This detects a PDF header and its declared format version from file bytes,
not from a filename, extension or MIME hint. A matching header is NOT a
structural validation, malware verdict, policy selection or opening approval.
The installed Built-in ClamAV gate remains the sole runtime scan authority.
"""

from dataclasses import dataclass
from enum import Enum
import os
import stat


class PDFFormatStatus(str, Enum):
    PDF_HEADER = "pdfHeader"
    NOT_PDF = "notPdf"
    UNDETERMINED = "undetermined"


@dataclass(frozen=True)
class PDFFormatIdentification:
    """Content-based header evidence; never an authorization to launch."""

    status: PDFFormatStatus
    version: str | None = None
    media_type: str | None = None

    @property
    def permits_open(self) -> bool:
        return False


NOT_PDF = PDFFormatIdentification(PDFFormatStatus.NOT_PDF)
UNDETERMINED = PDFFormatIdentification(PDFFormatStatus.UNDETERMINED)

# PDF 1.0–1.7 and ISO 32000-2 (PDF 2.0) have a versioned first-line marker.
# Only the first nine bytes are needed to identify a complete header line.
_PDF_VERSIONS = frozenset({*(f"1.{minor}" for minor in range(8)), "2.0"})
_PDF_PREFIX = b"%PDF-"
_HEADER_BYTES = 9


def identify_pdf_header(prefix: bytes) -> PDFFormatIdentification:
    """Identify only an exact first-line PDF signature in supplied bytes.

    This deliberately does not scan past an arbitrary prefix for embedded PDF
    markers: arbitrary leading bytes can describe a non-PDF/polyglot file.
    Further PDF structure and feature checks are separately planned.
    """
    if not isinstance(prefix, bytes):
        raise TypeError("A byte string is required for PDF format identification.")
    header = prefix[:_HEADER_BYTES]
    if len(header) < len(_PDF_PREFIX) and _PDF_PREFIX.startswith(header):
        return UNDETERMINED
    if not header.startswith(_PDF_PREFIX):
        return NOT_PDF
    if len(header) < _HEADER_BYTES:
        return UNDETERMINED
    try:
        version = header[5:8].decode("ascii")
    except UnicodeDecodeError:
        return UNDETERMINED
    if version not in _PDF_VERSIONS or header[8:9] not in (b"\n", b"\r"):
        return UNDETERMINED
    return PDFFormatIdentification(PDFFormatStatus.PDF_HEADER, version,
                                   "application/pdf")


def identify_pdf_format(path: os.PathLike[str] | str) -> PDFFormatIdentification:
    """Read at most nine bytes of a regular file, without changing its state.

    Never follow a final symlink or block on a FIFO. Unreadable, missing,
    changed, or unsupported file types yield no trusted format identification.
    No source paths or content are included in the result.
    """
    descriptor = None
    try:
        descriptor = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
        before = os.fstat(descriptor)
        if not stat.S_ISREG(before.st_mode):
            return UNDETERMINED
        with os.fdopen(descriptor, "rb") as source:
            descriptor = None
            prefix = source.read(_HEADER_BYTES)
            after = os.fstat(source.fileno())
        identity = lambda item: (item.st_dev, item.st_ino, item.st_size,
                                 item.st_mtime_ns, item.st_ctime_ns)
        if identity(before) != identity(after):
            return UNDETERMINED
        return identify_pdf_header(prefix)
    except (OSError, TypeError, ValueError):
        return UNDETERMINED
    finally:
        if descriptor is not None:
            os.close(descriptor)
