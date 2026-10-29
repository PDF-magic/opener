"""Read PDF document structure with the maintained pypdf parser (opener-0283).

This is a callable, fail-closed Enhanced-protection building block, NOT an
active profile or a file-opening verdict. It never opens filesystem paths,
decrypts documents, runs page content, or changes the established ClamAV,
quarantine, cache, and launch gates. The caller must separately enforce the
scan-time budget and verify the same file bytes before any future handoff.
"""

from dataclasses import dataclass
from enum import Enum
from io import BytesIO
import re


MAX_STRUCTURE_INPUT_BYTES = 16 * 1024 * 1024
MAX_STRUCTURE_PAGES = 1024
MAX_STRUCTURE_OBJECTS = 4096
_HEADER = re.compile(rb"\A%PDF-(1\.[0-7]|2\.0)[\r\n]")
_ERROR = "PDF structure could not be verified; opening was stopped."
_ENCRYPTED = "Encrypted PDF structure cannot be inspected; opening was stopped."
_DEPENDENCY = "The PDF structure parser is unavailable; opening was stopped."
_SIZE = "The PDF exceeds the structure inspection limit; opening was stopped."


class PDFStructureParseError(RuntimeError):
    """A non-clean structural result with no private PDF content in the message."""


@dataclass(frozen=True)
class PDFStructure:
    """Validated, immutable parser evidence; never an opening authorization.

    Version 1 of the JSON contract intentionally exposes only known metadata:
    PDF version and bounded page count. PDF-controlled strings, document paths,
    attachment names, page content and parser exception text are excluded.
    """

    pdf_version: str
    page_count: int

    def __post_init__(self):
        allowed_versions = {*(f"1.{minor}" for minor in range(8)), "2.0"}
        if type(self.pdf_version) is not str or self.pdf_version not in allowed_versions:
            raise ValueError("Unsupported PDF structural version")
        if type(self.page_count) is not int or not 1 <= self.page_count <= MAX_STRUCTURE_PAGES:
            raise ValueError("Invalid PDF structural page count")

    def to_dict(self) -> dict[str, str | int | bool]:
        """Return a detached, stable and JSON-serializable output record."""
        return {
            "schemaVersion": 1,
            "pdfVersion": self.pdf_version,
            "pageCount": self.page_count,
            "authorizesOpen": False,
        }


class PDFStructureFailureCode(str, Enum):
    """Trusted, path-free failure categories, never sourced from PDF strings."""

    invalidInput = "invalidInput"
    invalidStructure = "invalidStructure"
    sizeLimit = "sizeLimit"
    encrypted = "encrypted"
    dependencyUnavailable = "dependencyUnavailable"


@dataclass(frozen=True)
class PDFStructureParseFailure:
    """Non-clean parser outcome that never represents permission to proceed."""

    code: PDFStructureFailureCode

    def __post_init__(self):
        if type(self.code) is not PDFStructureFailureCode:
            raise TypeError("A known parsing failure code is required")

    def to_dict(self) -> dict[str, str | int | bool]:
        """Return detached, bounded, JSON-compatible diagnostic metadata."""
        return {
            "schemaVersion": 1,
            "status": "failure",
            "failureCode": self.code.value,
            "authorizesOpen": False,
        }


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
        # Check the complete indirect-object index before stream validation
        # and graph traversal; object streams have their own index entries.
        total_objects = sum(len(entries) for entries in reader.xref.values())
        total_objects += len(reader.xref_objStm)
        if total_objects > MAX_STRUCTURE_OBJECTS:
            raise PDFStructureParseError(_SIZE)
        # Check original bytes, not a library-recovered stream payload.
        from pdf_stream_lengths import validate_pdf_stream_lengths
        validate_pdf_stream_lengths(contents, reader)
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

# Map only fixed error messages created by this module. The wrapper never
# serializes exception text, raw input, filenames, object values, or paths.
_FAILURE_CODES = {
    _ERROR: PDFStructureFailureCode.invalidStructure,
    _ENCRYPTED: PDFStructureFailureCode.encrypted,
    _DEPENDENCY: PDFStructureFailureCode.dependencyUnavailable,
    _SIZE: PDFStructureFailureCode.sizeLimit,
}


def parse_pdf_structure_result(contents: bytes) -> PDFStructure | PDFStructureParseFailure:
    """Return strict parsing evidence or a structured, fail-closed failure.

    Keep parse_pdf_structure's existing exception behavior for older callers.
    This explicit result-based API is optional and does not authorize opening,
    cache reuse, profile activation, or any change to the installed scan gate.
    """
    if type(contents) is not bytes:
        return PDFStructureParseFailure(PDFStructureFailureCode.invalidInput)
    try:
        return parse_pdf_structure(contents)
    except PDFStructureParseError as error:
        return PDFStructureParseFailure(
            _FAILURE_CODES.get(str(error), PDFStructureFailureCode.invalidStructure)
        )
