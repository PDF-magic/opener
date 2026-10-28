"""Measure PDF stream decompression requirements without unbounded decoding.

Optional Enhanced-stage evidence only. Never an opening verdict and never part
of the deployed Built-in ClamAV, quarantine or browser handoff path.
"""

from dataclasses import dataclass
from io import BytesIO
import re
import zlib


MAX_INPUT_BYTES = 16 * 1024 * 1024
MAX_OBJECTS = 8192
MAX_STREAMS = 2048
MAX_STREAM_DECODED_BYTES = 8 * 1024 * 1024
MAX_TOTAL_DECODED_BYTES = 32 * 1024 * 1024
MAX_EXPANSION_RATIO = 200
MAX_PAGES = 1024

_INVALID = "PDF decompression requirements could not be inspected; opening was stopped."
_EXCESSIVE = "PDF decompression requirements exceed inspection limits; opening was stopped."
_UNAVAILABLE = "PDF decompression inspector is unavailable; opening was stopped."
_HEADER = re.compile(rb"\A%PDF-(1\.[0-7]|2\.0)[\r\n]")


class PDFDecompressionInspectionError(RuntimeError):
    """Non-clean outcome. Its fixed message never includes PDF content."""


@dataclass(frozen=True)
class PDFDecompressionInspection:
    """Bounded stream evidence only; never permission to open the PDF."""

    stream_count: int
    flate_stream_count: int
    decoded_bytes: int
    maximum_expansion_ratio: int
    permits_open: bool = False

    def __post_init__(self):
        if (any(type(value) is not int or value < 0 for value in (
                self.stream_count, self.flate_stream_count,
                self.decoded_bytes, self.maximum_expansion_ratio)) or
                self.flate_stream_count > self.stream_count or
                self.permits_open is not False):
            raise ValueError("Decompression inspection is not an opening verdict")


def _stream_size(raw, filter_name, decode_params, remaining):
    """Measure one stream with a capped zlib output allocation."""
    if type(raw) is not bytes or len(raw) > MAX_INPUT_BYTES:
        raise PDFDecompressionInspectionError(_INVALID)
    if filter_name is None:
        return len(raw), False, 1 if raw else 0
    if filter_name != "/FlateDecode" or decode_params is not None:
        # Unknown filter chains/predictors may expand arbitrarily. Refuse to
        # claim a complete analysis; never silently skip these streams.
        raise PDFDecompressionInspectionError(_INVALID)
    if not raw:
        raise PDFDecompressionInspectionError(_INVALID)

    limit = min(
        MAX_STREAM_DECODED_BYTES,
        MAX_EXPANSION_RATIO * len(raw),
        remaining,
    )
    try:
        inflater = zlib.decompressobj()
        # A strict output cap also bounds peak expansion memory. No flush()
        # and no PDF-library stream-decoding API is invoked.
        data = inflater.decompress(raw, limit + 1)
    except zlib.error:
        raise PDFDecompressionInspectionError(_INVALID) from None
    if len(data) > limit or inflater.unconsumed_tail:
        raise PDFDecompressionInspectionError(_EXCESSIVE)
    if not inflater.eof or inflater.unused_data:
        raise PDFDecompressionInspectionError(_INVALID)
    size = len(data)
    return size, True, (size + len(raw) - 1) // len(raw)


def inspect_pdf_decompression_requirements(contents: bytes) -> PDFDecompressionInspection:
    """Inspect every classic-xref PDF stream, including unreferenced objects.

    Input must already be immutable, verified bytes. Object streams and XRef
    streams are unsupported: parsing them may itself cause implicit unbounded
    expansion in the PDF library. A future isolated worker is required before
    accepting arbitrary adversarial documents in an active Enhanced pipeline.
    """
    if (type(contents) is not bytes or len(contents) > MAX_INPUT_BYTES or
            not _HEADER.match(contents[:9]) or
            b"%%EOF" not in contents[-1024:]):
        raise PDFDecompressionInspectionError(_INVALID)

    # Reject xref streams *before* PdfReader, since it may decompress those
    # during construction. A classic startxref points to literal 'xref'.
    match = re.search(rb"startxref\s+(\d+)\s+%%EOF\s*\Z", contents[-1024:])
    if match is None:
        raise PDFDecompressionInspectionError(_INVALID)
    offset = int(match.group(1))
    if offset >= len(contents) or contents[offset:offset + 4] != b"xref":
        raise PDFDecompressionInspectionError(_INVALID)

    try:
        from pypdf import PdfReader
        from pypdf.generic import IndirectObject, StreamObject
    except (ImportError, OSError):
        raise PDFDecompressionInspectionError(_UNAVAILABLE) from None

    try:
        reader = PdfReader(BytesIO(contents), strict=True)
        if reader.is_encrypted or reader.xref_objStm:
            raise PDFDecompressionInspectionError(_INVALID)
        if not 1 <= len(reader.pages) <= MAX_PAGES:
            raise PDFDecompressionInspectionError(_INVALID)
        objects = [(number, generation) for generation, entries in reader.xref.items()
                   for number in entries if number > 0]
        if len(objects) > MAX_OBJECTS:
            raise PDFDecompressionInspectionError(_EXCESSIVE)

        count = flate_count = decoded_total = highest_ratio = 0
        for number, generation in objects:
            obj = reader.get_object(IndirectObject(number, generation, reader))
            if not isinstance(obj, StreamObject):
                continue
            count += 1
            if count > MAX_STREAMS:
                raise PDFDecompressionInspectionError(_EXCESSIVE)
            remaining = MAX_TOTAL_DECODED_BYTES - decoded_total
            # No /Filter array, unsupported codec, predictor, or indirect
            # decoding parameter is treated as a verified bounded stream.
            length, flate, ratio = _stream_size(
                obj._data, obj.get("/Filter"), obj.get("/DecodeParms"), remaining
            )
            decoded_total += length
            flate_count += flate
            highest_ratio = max(highest_ratio, ratio)
            if decoded_total > MAX_TOTAL_DECODED_BYTES:
                raise PDFDecompressionInspectionError(_EXCESSIVE)
    except PDFDecompressionInspectionError:
        raise
    except Exception:
        # Never echo PDF-supplied text, filenames or parser diagnostics.
        raise PDFDecompressionInspectionError(_INVALID) from None

    return PDFDecompressionInspection(count, flate_count, decoded_total, highest_ratio)
