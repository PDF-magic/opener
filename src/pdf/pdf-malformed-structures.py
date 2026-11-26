"""Passive, bounded syntax-integrity inspection for a future Enhanced PDF stage.

This stage does not grant permission to open a PDF or replace the active
ClamAV scan. No PDF-supplied commands, links or streams are executed/decoded.
"""
from dataclasses import dataclass
from io import BytesIO
import re

MAX_PDF_BYTES = 16 * 1024 * 1024
MAX_OBJECTS = 4096
MAX_PAGES = 1024
BLOCK_MESSAGE = "PDF structural integrity could not be verified; opening was stopped."
_HEADER = re.compile(rb"\A%PDF-(?:1\.[0-7]|2\.0)[\r\n]")
_END = re.compile(rb"startxref\s+([0-9]+)\s+%%EOF[ \t\r\n]*\Z")


class PDFMalformedStructureError(RuntimeError):
    """Fixed, content-free failure to completely inspect PDF syntax."""


@dataclass(frozen=True)
class PDFMalformedStructureInspection:
    object_count: int
    page_count: int
    malformed: bool = False
    permits_open: bool = False

    def __post_init__(self):
        if (type(self.object_count) is not int or not 1 <= self.object_count <= MAX_OBJECTS
                or type(self.page_count) is not int or not 1 <= self.page_count <= MAX_PAGES
                or self.malformed is not False or self.permits_open is not False):
            raise ValueError("Structural inspection never grants opening permission")


def inspect_pdf_malformed_structures(contents: bytes) -> PDFMalformedStructureInspection:
    """Check PDF framing, strict parser objects, xref offsets and basic roots.

    This deliberately does not validate graph semantics, incremental revision
    histories, automatic actions, embedded payloads or stream decompression:
    those are separate Enhanced stages. It rejects unsupported xref streams.
    """
    if type(contents) is not bytes or not contents or len(contents) > MAX_PDF_BYTES:
        raise PDFMalformedStructureError(BLOCK_MESSAGE)
    if not _HEADER.match(contents[:9]):
        raise PDFMalformedStructureError(BLOCK_MESSAGE)
    end = _END.search(contents[-2048:])
    if end is None:
        raise PDFMalformedStructureError(BLOCK_MESSAGE)
    try:
        startxref = int(end.group(1))
        if not 0 < startxref < len(contents) or contents[startxref:startxref + 4] != b"xref":
            raise PDFMalformedStructureError(BLOCK_MESSAGE)
        from pypdf import PdfReader
        from pypdf.generic import DictionaryObject, IndirectObject
        reader = PdfReader(BytesIO(contents), strict=True)
        if reader.is_encrypted or reader.xref_objStm:
            raise PDFMalformedStructureError(BLOCK_MESSAGE)
        trailer = reader.trailer
        size = trailer.raw_get("/Size")
        root_ref = trailer.raw_get("/Root")
        if (not isinstance(size, int) or isinstance(size, bool)
                or not 2 <= size <= MAX_OBJECTS + 1):
            raise PDFMalformedStructureError(BLOCK_MESSAGE)
        if not isinstance(root_ref, IndirectObject):
            raise PDFMalformedStructureError(BLOCK_MESSAGE)
        root = root_ref.get_object()
        if (not isinstance(root, DictionaryObject) or root.get("/Type") != "/Catalog"
                or "/Pages" not in root):
            raise PDFMalformedStructureError(BLOCK_MESSAGE)
        total = 0
        highest = 0
        for generation, group in reader.xref.items():
            if type(generation) is not int or not 0 <= generation <= 65535:
                raise PDFMalformedStructureError(BLOCK_MESSAGE)
            for number, offset in group.items():
                if number == 0:
                    continue
                if (type(number) is not int or type(offset) is not int
                        or number < 1 or not 0 < offset < startxref):
                    raise PDFMalformedStructureError(BLOCK_MESSAGE)
                total += 1
                highest = max(highest, number)
                if total > MAX_OBJECTS or number >= size:
                    raise PDFMalformedStructureError(BLOCK_MESSAGE)
                # Do not accept a parser-recovered offset unless its actual
                # byte position contains the corresponding object header.
                header = re.match(rb"\s*%d\s+%d\s+obj\b" % (number, generation),
                                  contents[offset:offset + 80])
                if header is None:
                    raise PDFMalformedStructureError(BLOCK_MESSAGE)
                item = reader.get_object(IndirectObject(number, generation, reader))
                if item is None:
                    raise PDFMalformedStructureError(BLOCK_MESSAGE)
        if total == 0 or root_ref.idnum > highest:
            raise PDFMalformedStructureError(BLOCK_MESSAGE)
        pages = reader.pages
        count = len(pages)
        if not 1 <= count <= MAX_PAGES:
            raise PDFMalformedStructureError(BLOCK_MESSAGE)
        for page in pages:
            if not isinstance(page, DictionaryObject) or page.get("/Type") != "/Page":
                raise PDFMalformedStructureError(BLOCK_MESSAGE)
        return PDFMalformedStructureInspection(total, count)
    except PDFMalformedStructureError:
        raise
    except Exception:
        raise PDFMalformedStructureError(BLOCK_MESSAGE) from None
