"""Fail-closed structural validation of a generated Maximum PDF (opener-0319).

Checks the *final* bytes before they may be offered as a sanitized copy.
This does not validate source documents, scan for malware, or authorize opening.
"""
from dataclasses import dataclass
from io import BytesIO
import math
import re
import zlib

MAX_OUTPUT_BYTES = 32 * 1024 * 1024
MAX_OUTPUT_PAGES = 16
MAX_OUTPUT_OBJECTS = 4096
MAX_PAGE_TREE_NODES = 8192
MAX_CONTENT_STREAM_BYTES = 2 * 1024 * 1024
MAX_CONTENT_DECODED_BYTES = 2 * 1024 * 1024
MAX_CONTENT_STREAMS = 256
BLOCK_MESSAGE = "Sanitized PDF structure could not be verified; no copy was offered."
_HEADER = re.compile(rb"\A%PDF-(?:1\.[0-7]|2\.0)[\r\n]")
_END = re.compile(rb"startxref[ \t\r\n]+([0-9]+)[ \t\r\n]+%%EOF[ \t\r\n]*\Z")


class SanitizedPDFStructureError(RuntimeError):
    """Fixed, path-free failure; never reveal PDF-controlled error messages."""


@dataclass(frozen=True)
class SanitizedPDFStructure:
    """Validated structure counts; not a PDF clean verdict or permission to open."""

    page_count: int
    object_count: int
    permits_open: bool = False

    def __post_init__(self):
        if (type(self.page_count) is not int or
                not 1 <= self.page_count <= MAX_OUTPUT_PAGES or
                type(self.object_count) is not int or
                not 1 <= self.object_count <= MAX_OUTPUT_OBJECTS or
                self.permits_open is not False):
            raise ValueError("Structural verification never authorizes opening")


def _bounded_content(stream):
    """Validate page content bytes without unbounded parser decompression."""
    from pypdf.generic import StreamObject
    if not isinstance(stream, StreamObject):
        raise SanitizedPDFStructureError(BLOCK_MESSAGE)
    raw = stream._data
    if type(raw) is not bytes or len(raw) > MAX_CONTENT_STREAM_BYTES:
        raise SanitizedPDFStructureError(BLOCK_MESSAGE)
    filter_name = stream.get("/Filter")
    if filter_name is None:
        return
    if filter_name != "/FlateDecode" or stream.get("/DecodeParms") is not None:
        raise SanitizedPDFStructureError(BLOCK_MESSAGE)
    try:
        inflater = zlib.decompressobj()
        decoded = inflater.decompress(raw, MAX_CONTENT_DECODED_BYTES + 1)
        if (len(decoded) > MAX_CONTENT_DECODED_BYTES or
                not inflater.eof or inflater.unconsumed_tail or
                inflater.unused_data):
            raise SanitizedPDFStructureError(BLOCK_MESSAGE)
    except zlib.error:
        raise SanitizedPDFStructureError(BLOCK_MESSAGE) from None


def verify_sanitized_pdf_structure(
    pdf_bytes: bytes, expected_pages: int,
) -> SanitizedPDFStructure:
    """Verify exact PDF framing, object xrefs, page hierarchy and page streams.

    Requires a single fully bounded classic cross-reference table; malformed,
    repaired, incremental, encrypted, truncated, and unsupported outputs fail
    closed. Only generated output is an input to this post-conversion gate.
    """
    if (type(pdf_bytes) is not bytes or
            not 0 < len(pdf_bytes) <= MAX_OUTPUT_BYTES or
            type(expected_pages) is not int or
            not 1 <= expected_pages <= MAX_OUTPUT_PAGES or
            not _HEADER.match(pdf_bytes[:9])):
        raise SanitizedPDFStructureError(BLOCK_MESSAGE)
    end = _END.search(pdf_bytes[-2048:])
    if end is None:
        raise SanitizedPDFStructureError(BLOCK_MESSAGE)
    startxref = int(end.group(1))
    if not 0 < startxref < len(pdf_bytes) or pdf_bytes[startxref:startxref + 4] != b"xref":
        raise SanitizedPDFStructureError(BLOCK_MESSAGE)

    try:
        from pypdf import PdfReader
        from pypdf.generic import (
            ArrayObject, DictionaryObject, IndirectObject, StreamObject,
        )
        reader = PdfReader(BytesIO(pdf_bytes), strict=True)
        if reader.is_encrypted or reader.xref_objStm or "/Prev" in reader.trailer:
            raise SanitizedPDFStructureError(BLOCK_MESSAGE)
        size = reader.trailer.raw_get("/Size")
        root_ref = reader.trailer.raw_get("/Root")
        if (type(size) is not int or not 2 <= size <= MAX_OUTPUT_OBJECTS + 1 or
                not isinstance(root_ref, IndirectObject)):
            raise SanitizedPDFStructureError(BLOCK_MESSAGE)

        indexed = 0
        for generation, offsets in reader.xref.items():
            if type(generation) is not int or not 0 <= generation <= 65535:
                raise SanitizedPDFStructureError(BLOCK_MESSAGE)
            for number, offset in offsets.items():
                if number == 0:
                    continue
                if (type(number) is not int or type(offset) is not int or
                        not 1 <= number < size or not 0 < offset < startxref):
                    raise SanitizedPDFStructureError(BLOCK_MESSAGE)
                indexed += 1
                if indexed > MAX_OUTPUT_OBJECTS:
                    raise SanitizedPDFStructureError(BLOCK_MESSAGE)
                header = re.match(
                    rb"\s*%d\s+%d\s+obj\b" % (number, generation),
                    pdf_bytes[offset:offset + 80],
                )
                if header is None or reader.get_object(
                    IndirectObject(number, generation, reader)
                ) is None:
                    raise SanitizedPDFStructureError(BLOCK_MESSAGE)

        root = root_ref.get_object()
        if (not isinstance(root, DictionaryObject) or
                root.get("/Type") != "/Catalog" or "/Pages" not in root):
            raise SanitizedPDFStructureError(BLOCK_MESSAGE)
        pages_ref = root.raw_get("/Pages")
        if not isinstance(pages_ref, IndirectObject):
            raise SanitizedPDFStructureError(BLOCK_MESSAGE)

        seen = set()
        leaf_count = 0
        stream_count = 0

        def walk(ref, parent=None):
            nonlocal leaf_count, stream_count
            if not isinstance(ref, IndirectObject):
                raise SanitizedPDFStructureError(BLOCK_MESSAGE)
            key = (ref.idnum, ref.generation)
            if key in seen or len(seen) >= MAX_PAGE_TREE_NODES:
                raise SanitizedPDFStructureError(BLOCK_MESSAGE)
            seen.add(key)
            node = ref.get_object()
            if not isinstance(node, DictionaryObject):
                raise SanitizedPDFStructureError(BLOCK_MESSAGE)
            if parent is not None:
                actual_parent = node.raw_get("/Parent") if "/Parent" in node else None
                if not isinstance(actual_parent, IndirectObject) or (
                    actual_parent.idnum, actual_parent.generation
                ) != (parent.idnum, parent.generation):
                    raise SanitizedPDFStructureError(BLOCK_MESSAGE)
            kind = node.get("/Type")
            if kind == "/Pages":
                children = node.raw_get("/Kids") if "/Kids" in node else None
                count = node.raw_get("/Count") if "/Count" in node else None
                if (not isinstance(children, ArrayObject) or
                        not 1 <= len(children) <= MAX_OUTPUT_PAGES or
                        type(count) is not int or not 1 <= count <= MAX_OUTPUT_PAGES):
                    raise SanitizedPDFStructureError(BLOCK_MESSAGE)
                total = sum(walk(child, ref) for child in children)
                if total != count:
                    raise SanitizedPDFStructureError(BLOCK_MESSAGE)
                return total
            if kind != "/Page" or parent is None:
                raise SanitizedPDFStructureError(BLOCK_MESSAGE)
            leaf_count += 1
            if leaf_count > MAX_OUTPUT_PAGES:
                raise SanitizedPDFStructureError(BLOCK_MESSAGE)
            media = node.get("/MediaBox")
            if not isinstance(media, ArrayObject) or len(media) != 4:
                raise SanitizedPDFStructureError(BLOCK_MESSAGE)
            rectangle = [float(x) for x in media]
            if (not all(math.isfinite(x) for x in rectangle) or
                    not 1 <= rectangle[2] - rectangle[0] <= 1440 or
                    not 1 <= rectangle[3] - rectangle[1] <= 1440):
                raise SanitizedPDFStructureError(BLOCK_MESSAGE)
            if "/Contents" in node:
                content = node.raw_get("/Contents")
                if isinstance(content, IndirectObject):
                    content = content.get_object()
                streams = content if isinstance(content, ArrayObject) else (content,)
                if len(streams) > MAX_CONTENT_STREAMS - stream_count:
                    raise SanitizedPDFStructureError(BLOCK_MESSAGE)
                for item in streams:
                    if isinstance(item, IndirectObject):
                        item = item.get_object()
                    if not isinstance(item, StreamObject):
                        raise SanitizedPDFStructureError(BLOCK_MESSAGE)
                    _bounded_content(item)
                    stream_count += 1
            return 1

        actual_count = walk(pages_ref)
        if (indexed < 2 or actual_count != expected_pages or
                len(reader.pages) != expected_pages):
            raise SanitizedPDFStructureError(BLOCK_MESSAGE)
        return SanitizedPDFStructure(actual_count, indexed)
    except SanitizedPDFStructureError:
        raise
    except Exception:
        # Parser errors may include private document data and file paths.
        raise SanitizedPDFStructureError(BLOCK_MESSAGE) from None
