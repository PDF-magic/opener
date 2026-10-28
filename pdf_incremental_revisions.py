"""Passive bounded inspection of PDF incremental revisions (opener-0291).

Inspection evidence is never authorization to open a document. No filesystem
path or PDF-provided action, stream, URL or script is executed.
"""
from dataclasses import dataclass
from io import BytesIO
import re
import zlib

MAX_PDF_BYTES = 16 * 1024 * 1024
MAX_REVISIONS = 64
MAX_XREF_ENTRIES = 8192
MAX_PAGES = 1024
BLOCK_MESSAGE = "PDF incremental revisions could not be verified; opening was stopped."
_END = re.compile(rb"startxref\s+(\d+)\s*%%EOF\s*\Z")
_ROW = re.compile(rb"(\d{10})\s+(\d{5})\s+([nf])\s*")
_SECTION = re.compile(rb"(\d+)\s+(\d+)")
_OBJECT = re.compile(rb"(\d+)\s+(\d+)\s+obj\b")


class PDFIncrementalRevisionError(RuntimeError):
    """Fixed, path-free uninspectable result."""


@dataclass(frozen=True)
class PDFIncrementalRevisionInspection:
    revision_count: int
    updated_object_count: int
    added_object_count: int
    xref_formats: tuple[str, ...]
    permits_open: bool = False

    def __post_init__(self):
        if (type(self.revision_count) is not int or
                not 1 <= self.revision_count <= MAX_REVISIONS or
                type(self.updated_object_count) is not int or
                not 0 <= self.updated_object_count <= MAX_XREF_ENTRIES or
                type(self.added_object_count) is not int or
                not 0 <= self.added_object_count <= MAX_XREF_ENTRIES or
                type(self.xref_formats) is not tuple or
                len(self.xref_formats) != self.revision_count or
                any(x not in ("table", "stream", "hybrid") for x in self.xref_formats) or
                self.permits_open is not False):
            raise ValueError("Revision metadata cannot authorize opening")

    @property
    def has_incremental_updates(self) -> bool:
        return self.revision_count > 1


def _number(value, bound):
    if not isinstance(value, int) or isinstance(value, bool) or not 0 <= value <= bound:
        raise PDFIncrementalRevisionError(BLOCK_MESSAGE)
    return value


def _stream_entries(obj):
    """Read only xref index bytes, with output limited before decompression."""
    from pypdf.generic import ArrayObject, DictionaryObject

    if obj.get("/Type") != "/XRef":
        raise PDFIncrementalRevisionError(BLOCK_MESSAGE)
    widths = obj.get("/W")
    if (not isinstance(widths, ArrayObject) or len(widths) != 3 or
            any(not isinstance(n, int) or isinstance(n, bool) or not 0 <= n <= 8
                for n in widths) or sum(widths) == 0):
        raise PDFIncrementalRevisionError(BLOCK_MESSAGE)
    size = _number(obj.get("/Size"), MAX_XREF_ENTRIES)
    index = obj.get("/Index", [0, size])
    if not isinstance(index, (list, ArrayObject)) or len(index) % 2:
        raise PDFIncrementalRevisionError(BLOCK_MESSAGE)
    ranges = []
    count = 0
    for start, length in zip(index[::2], index[1::2]):
        start = _number(start, size)
        length = _number(length, size)
        if start + length > size or count + length > MAX_XREF_ENTRIES:
            raise PDFIncrementalRevisionError(BLOCK_MESSAGE)
        ranges.append((start, length))
        count += length
    needed = count * sum(widths)
    params = obj.get("/DecodeParms")
    if params is not None and (not isinstance(params, DictionaryObject) or
                               params.get("/Predictor", 1) != 1):
        raise PDFIncrementalRevisionError(BLOCK_MESSAGE)
    original = obj._data
    if type(original) is not bytes or len(original) > MAX_PDF_BYTES:
        raise PDFIncrementalRevisionError(BLOCK_MESSAGE)
    filt = obj.get("/Filter")
    if filt is None:
        decoded = original
    elif filt == "/FlateDecode":
        decoder = zlib.decompressobj()
        decoded = decoder.decompress(original, needed + 1)
        if (len(decoded) != needed or not decoder.eof or
                decoder.unconsumed_tail or decoder.unused_data or decoder.flush(1)):
            raise PDFIncrementalRevisionError(BLOCK_MESSAGE)
    else:
        raise PDFIncrementalRevisionError(BLOCK_MESSAGE)
    if len(decoded) != needed:
        raise PDFIncrementalRevisionError(BLOCK_MESSAGE)

    found = set()
    position = 0
    for start, length in ranges:
        for number in range(start, start + length):
            fields = []
            for width in widths:
                fields.append(int.from_bytes(decoded[position:position + width], "big")
                              if width else 0)
                position += width
            kind, first, generation = fields
            if widths[0] == 0:
                kind = 1
            if kind == 1:
                if first <= 0 or first >= MAX_PDF_BYTES or generation > 65535:
                    raise PDFIncrementalRevisionError(BLOCK_MESSAGE)
                found.add(number)
            elif kind == 2:
                if not 0 < first < MAX_XREF_ENTRIES:
                    raise PDFIncrementalRevisionError(BLOCK_MESSAGE)
                found.add(number)
            elif kind != 0:
                raise PDFIncrementalRevisionError(BLOCK_MESSAGE)
    return found


def _read_xref(contents, offset, reader):
    """Find the xref section at the declared offset, including /Prev."""
    from pypdf.generic import DictionaryObject, StreamObject, read_object

    _number(offset, len(contents) - 1)
    stream = BytesIO(contents)
    stream.seek(offset)
    objects = set()
    if stream.readline().strip() == b"xref":
        sections = 0
        entries = 0
        while True:
            line = stream.readline().strip()
            if not line:
                raise PDFIncrementalRevisionError(BLOCK_MESSAGE)
            if line == b"trailer":
                break
            sections += 1
            if sections > 128:
                raise PDFIncrementalRevisionError(BLOCK_MESSAGE)
            header = _SECTION.fullmatch(line)
            if header is None:
                raise PDFIncrementalRevisionError(BLOCK_MESSAGE)
            start, length = (int(x) for x in header.groups())
            entries += length
            if (entries > MAX_XREF_ENTRIES or start > MAX_XREF_ENTRIES or
                    length > MAX_XREF_ENTRIES or start + length > MAX_XREF_ENTRIES):
                raise PDFIncrementalRevisionError(BLOCK_MESSAGE)
            for number in range(start, start + length):
                row = _ROW.fullmatch(stream.readline().strip())
                if row is None:
                    raise PDFIncrementalRevisionError(BLOCK_MESSAGE)
                physical_offset, generation, status = row.groups()
                if status == b"n":
                    if not 0 < int(physical_offset) < offset or number in objects:
                        raise PDFIncrementalRevisionError(BLOCK_MESSAGE)
                    objects.add(number)
        trailer = read_object(stream, reader)
        if not isinstance(trailer, DictionaryObject):
            raise PDFIncrementalRevisionError(BLOCK_MESSAGE)
        kind = "table"
        if "/XRefStm" in trailer:
            hybrid = _number(trailer.raw_get("/XRefStm"), len(contents) - 1)
            supplement, _, subtype = _read_xref(contents, hybrid, reader)
            if subtype != "stream" or hybrid == offset:
                raise PDFIncrementalRevisionError(BLOCK_MESSAGE)
            objects.update(supplement)
            kind = "hybrid"
    else:
        stream.seek(offset)
        header = _OBJECT.match(stream.read(64))
        if header is None or int(header.group(2)) != 0:
            raise PDFIncrementalRevisionError(BLOCK_MESSAGE)
        stream.seek(offset + header.end())
        trailer = read_object(stream, reader)
        if not isinstance(trailer, StreamObject):
            raise PDFIncrementalRevisionError(BLOCK_MESSAGE)
        objects = _stream_entries(trailer)
        kind = "stream"
    prev = trailer.raw_get("/Prev") if "/Prev" in trailer else None
    if prev is not None:
        prev = _number(prev, len(contents) - 1)
        if prev >= offset:
            raise PDFIncrementalRevisionError(BLOCK_MESSAGE)
    return objects, prev, kind


def inspect_pdf_incremental_revisions(contents: bytes) -> PDFIncrementalRevisionInspection:
    """Follow historical /Prev pointers, not just the latest object graph."""
    if type(contents) is not bytes or not contents or len(contents) > MAX_PDF_BYTES:
        raise PDFIncrementalRevisionError(BLOCK_MESSAGE)
    if not re.match(rb"\A%PDF-(1\.[0-7]|2\.0)[\r\n]", contents[:9]):
        raise PDFIncrementalRevisionError(BLOCK_MESSAGE)
    final = _END.search(contents)
    if final is None:
        raise PDFIncrementalRevisionError(BLOCK_MESSAGE)
    try:
        from pypdf import PdfReader
        reader = PdfReader(BytesIO(contents), strict=True)
        if reader.is_encrypted or reader.xref_objStm or not 1 <= len(reader.pages) <= MAX_PAGES:
            raise PDFIncrementalRevisionError(BLOCK_MESSAGE)
        if reader.trailer["/Root"].get("/Type") != "/Catalog":
            raise PDFIncrementalRevisionError(BLOCK_MESSAGE)
        offset = int(final.group(1))
        seen = set()
        revisions = []
        while True:
            if offset in seen or len(revisions) >= MAX_REVISIONS:
                raise PDFIncrementalRevisionError(BLOCK_MESSAGE)
            seen.add(offset)
            objects, previous, kind = _read_xref(contents, offset, reader)
            revisions.append((objects, kind))
            if previous is None:
                break
            historical_eof = re.search(
                rb"startxref\s+" + str(previous).encode("ascii") +
                rb"\s*%%EOF\b", contents[:offset],
            )
            if historical_eof is None:
                raise PDFIncrementalRevisionError(BLOCK_MESSAGE)
            offset = previous
        indexed, updated, added = set(), set(), set()
        for i, (objects, _) in enumerate(reversed(revisions)):
            if i:
                updated.update(objects & indexed)
                added.update(objects - indexed)
            indexed.update(objects)
        return PDFIncrementalRevisionInspection(
            len(revisions), len(updated), len(added),
            tuple(kind for _, kind in reversed(revisions)),
        )
    except PDFIncrementalRevisionError:
        raise
    except Exception:
        raise PDFIncrementalRevisionError(BLOCK_MESSAGE) from None
