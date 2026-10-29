"""Read PDF document structure with the maintained pypdf parser (opener-0283).

This is a callable, fail-closed Enhanced-protection building block, NOT an
active profile or a file-opening verdict. It never opens filesystem paths,
decrypts documents, runs page content, or changes the established ClamAV,
quarantine, cache, and launch gates. The caller must separately enforce the
scan-time budget and verify the same file bytes before any future handoff.
"""

from dataclasses import dataclass
from io import BytesIO
import re


MAX_STRUCTURE_INPUT_BYTES = 16 * 1024 * 1024
MAX_STRUCTURE_PAGES = 1024
_HEADER = re.compile(rb"\A%PDF-(1\.[0-7]|2\.0)[\r\n]")
_ERROR = "PDF structure could not be verified; opening was stopped."
_ENCRYPTED = "Encrypted PDF structure cannot be inspected; opening was stopped."
_DEPENDENCY = "The PDF structure parser is unavailable; opening was stopped."
_SIZE = "The PDF exceeds the structure inspection limit; opening was stopped."


class PDFStructureParseError(RuntimeError):
    """A non-clean structural result with no private PDF content in the message."""


@dataclass(frozen=True)
class PDFStructure:
    """Parsed structural evidence only. Never permission to open a document."""

    pdf_version: str
    page_count: int


def parse_pdf_structure(contents: bytes) -> PDFStructure:
    """Parse an in-memory PDF with pypdf's strict object and page-tree reader.

    Accept bytes only: callers must read and validate a file through the
    existing secure file-handling workflow. The strict pypdf reader resolves
    traditional cross-reference tables, PDF 1.5 cross-reference streams, and
    compressed objects in object streams as needed to traverse the page tree.
    Avoid decoding page content streams, following attachments/links, or
    invoking user-specified applications.
    """
    if type(contents) is not bytes:
        raise PDFStructureParseError(_ERROR)
    if len(contents) > MAX_STRUCTURE_INPUT_BYTES:
        raise PDFStructureParseError(_SIZE)
    header = _HEADER.match(contents[:9])
    if header is None or b"%%EOF" not in contents[-1024:]:
        raise PDFStructureParseError(_ERROR)

    try:
        from pypdf import PdfReader
    except (ImportError, OSError):
        raise PDFStructureParseError(_DEPENDENCY) from None

    try:
        reader = PdfReader(BytesIO(contents), strict=True)
        if reader.is_encrypted:
            raise PDFStructureParseError(_ENCRYPTED)
        root = reader.trailer["/Root"]
        if root.get("/Type") != "/Catalog":
            raise PDFStructureParseError(_ERROR)
        pages = reader.pages
        count = len(pages)
        if count < 1 or count > MAX_STRUCTURE_PAGES:
            raise PDFStructureParseError(_ERROR)
        for page in pages:
            if page.get("/Type") != "/Page":
                raise PDFStructureParseError(_ERROR)
    except PDFStructureParseError:
        raise
    except Exception:
        # pypdf error details may contain untrusted PDF strings or filenames.
        raise PDFStructureParseError(_ERROR) from None

    return PDFStructure(pdf_version=header.group(1).decode("ascii"), page_count=count)
