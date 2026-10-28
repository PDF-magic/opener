"""Fail-closed structural-ambiguity evidence for a future Enhanced PDF stage.

This bounded, in-memory preflight never provides a clean verdict or opens files.
It is not called by the installed Built-in ClamAV scan gate. A future Enhanced
worker must add execution-time and memory isolation before using it on inputs.
"""

from dataclasses import dataclass
from io import BytesIO
import re

MAX_PDF_BYTES = 16 * 1024 * 1024
MAX_XREF_OBJECTS = 4096
BLOCK_MESSAGE = "PDF structure could not be unambiguously inspected; opening was stopped."

# Require a complete final trailer. Bytes beyond EOF can change which PDF a
# viewer opens; older EOF markers from valid incremental updates are allowed.
_FINAL_TRAILER = re.compile(rb"(?:^|[\r\n])startxref[ \t\r\n]+([0-9]{1,16})[ \t\r\n]+%%EOF[ \t\r\n]*\Z")
_OBJECT_HEADER = re.compile(rb"([0-9]+)[ \t\r\n]+([0-9]+)[ \t\r\n]+obj\b")


class PDFStructureAmbiguityError(RuntimeError):
    """Incomplete or contradictory structure is not a clean outcome."""


@dataclass(frozen=True)
class PDFStructureAmbiguityInspection:
    """Read-only evidence, never approval to open a PDF."""

    inspected_objects: int
    ambiguous: bool = False
    permits_open: bool = False

    def __post_init__(self):
        if (type(self.inspected_objects) is not int or self.inspected_objects < 0
                or self.ambiguous is not False or self.permits_open is not False):
            raise ValueError("Structural inspection cannot approve a document.")


def inspect_pdf_structure_ambiguity(contents: bytes) -> PDFStructureAmbiguityInspection:
    """Reject conflicting cross-reference targets, object keys and EOF framing.

    Strict pypdf object parsing detects duplicate dictionary keys, and every
    traditional xref target is checked against its *actual* object header.
    Reject unsupported compressed objects rather than silently skipping them.
    This does not inspect incremental-revision history or establish PDF safety.
    """
    if type(contents) is not bytes or not 0 < len(contents) <= MAX_PDF_BYTES:
        raise PDFStructureAmbiguityError(BLOCK_MESSAGE)
    try:
        from pypdf import PdfReader
        from pypdf.generic import IndirectObject, DictionaryObject

        tail = _FINAL_TRAILER.search(contents)
        if tail is None:
            raise PDFStructureAmbiguityError(BLOCK_MESSAGE)
        startxref = int(tail.group(1))
        if not 0 < startxref < len(contents):
            raise PDFStructureAmbiguityError(BLOCK_MESSAGE)
        start = contents[startxref: startxref + 80]
        if not (start.startswith(b"xref") and (len(start) == 4 or start[4:5] in b" \r\n\t")
                or (_OBJECT_HEADER.match(start) is not None)):
            raise PDFStructureAmbiguityError(BLOCK_MESSAGE)

        reader = PdfReader(BytesIO(contents), strict=True)
        if reader.is_encrypted or reader.xref_objStm:
            raise PDFStructureAmbiguityError(BLOCK_MESSAGE)
        if not isinstance(reader.trailer.get("/Root"), (IndirectObject, DictionaryObject)):
            raise PDFStructureAmbiguityError(BLOCK_MESSAGE)

        offsets = set()
        count = 0
        for generation, objects in reader.xref.items():
            if type(generation) is not int or not 0 <= generation <= 65535:
                raise PDFStructureAmbiguityError(BLOCK_MESSAGE)
            for number, offset in objects.items():
                count += 1
                if (count > MAX_XREF_OBJECTS or not isinstance(number, int)
                        or number <= 0):
                    raise PDFStructureAmbiguityError(BLOCK_MESSAGE)
                if not isinstance(offset, int) or not 0 < offset < startxref:
                    raise PDFStructureAmbiguityError(BLOCK_MESSAGE)
                header = _OBJECT_HEADER.match(contents, offset)
                if (header is None or int(header.group(1)) != number
                        or int(header.group(2)) != generation or offset in offsets):
                    raise PDFStructureAmbiguityError(BLOCK_MESSAGE)
                offsets.add(offset)
                # Eagerly parse unreferenced objects too: duplicate dictionary
                # keys and unreadable objects must not remain hidden.
                if reader.get_object(IndirectObject(number, generation, reader)) is None:
                    raise PDFStructureAmbiguityError(BLOCK_MESSAGE)

        if count == 0 or not isinstance(reader.trailer["/Root"].get_object(), DictionaryObject):
            raise PDFStructureAmbiguityError(BLOCK_MESSAGE)
        return PDFStructureAmbiguityInspection(count)
    except PDFStructureAmbiguityError:
        raise
    except Exception as exc:
        # Never expose parser diagnostics, extracted strings or caller content.
        raise PDFStructureAmbiguityError(BLOCK_MESSAGE) from exc
