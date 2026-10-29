"""Report unusually large PDF stream and embedded-object sizes without execution.

This passive Enhanced-only detector never replaces the installed ClamAV gate,
grants opening, writes attachments, or infers safety from a small object.
"""
from dataclasses import dataclass
from io import BytesIO
import zlib

from pdf_structure_parser import parse_pdf_structure

MAX_OBJECTS = 4096
MAX_STREAMS = 2048
MAX_ATTACHMENTS = 32
LARGE_ENCODED_BYTES = 1024 * 1024
LARGE_DECODED_BYTES = 1024 * 1024
LARGE_DECLARED_BYTES = 1024 * 1024
HIGH_EXPANSION_RATIO = 100
BLOCK_MESSAGE = "Embedded PDF object sizes could not be fully inspected; opening was stopped."


class PDFEmbeddedObjectSizeError(RuntimeError):
    """Incomplete size inspection is a non-clean result without source data."""


@dataclass(frozen=True)
class PDFEmbeddedObjectSizes:
    stream_count: int
    embedded_stream_count: int
    large_encoded_count: int
    large_decoded_count: int
    high_expansion_count: int
    large_declared_count: int
    permits_open: bool = False

    def __post_init__(self):
        values = (self.stream_count, self.embedded_stream_count,
                  self.large_encoded_count, self.large_decoded_count,
                  self.high_expansion_count, self.large_declared_count)
        if (any(type(x) is not int or not 0 <= x <= MAX_STREAMS for x in values)
                or self.embedded_stream_count > self.stream_count
                or self.large_encoded_count > self.stream_count
                or any(x > self.embedded_stream_count for x in
                       (self.large_decoded_count, self.high_expansion_count,
                        self.large_declared_count))
                or self.permits_open is not False):
            raise ValueError("Object-size evidence cannot authorize opening")

    @property
    def has_large_objects(self):
        return bool(self.large_encoded_count or self.large_decoded_count
                    or self.high_expansion_count or self.large_declared_count)


def _embedded_size(stream, stream_type):
    """Bound output to the threshold plus one byte; never decode full bombs."""
    raw = stream._data
    if type(raw) is not bytes:
        raise PDFEmbeddedObjectSizeError(BLOCK_MESSAGE)
    filters = stream.get("/Filter")
    params = stream.get("/DecodeParms")
    if filters is None:
        return len(raw), False
    if filters != "/FlateDecode" or params is not None:
        raise PDFEmbeddedObjectSizeError(BLOCK_MESSAGE)
    if not raw:
        raise PDFEmbeddedObjectSizeError(BLOCK_MESSAGE)
    try:
        inflater = zlib.decompressobj()
        part = inflater.decompress(raw, LARGE_DECODED_BYTES + 1)
    except zlib.error:
        raise PDFEmbeddedObjectSizeError(BLOCK_MESSAGE) from None
    if len(part) > LARGE_DECODED_BYTES:
        # Deliberately stop early. An oversized stream is suspicious evidence,
        # not a complete validation, clean verdict or authorization to open.
        return len(part), True
    if not inflater.eof or inflater.unused_data or inflater.unconsumed_tail:
        raise PDFEmbeddedObjectSizeError(BLOCK_MESSAGE)
    return len(part), True


def inspect_pdf_embedded_object_sizes(contents: bytes) -> PDFEmbeddedObjectSizes:
    """Inspect all traditional-xref streams, even orphans, and attached bytes.

    The shared strict structure parser first validates stream lengths. To avoid
    decompressing xref/object streams implicitly, unsupported xref-object-stream
    documents are a fixed failure until they can run in a hardened worker.
    """
    try:
        parse_pdf_structure(contents)
        from pypdf import PdfReader
        from pypdf.generic import DictionaryObject, IndirectObject, StreamObject
        from enhanced_embedded_files import _resolve, _specifications

        reader = PdfReader(BytesIO(contents), strict=True)
        if reader.is_encrypted or reader.xref_objStm:
            raise PDFEmbeddedObjectSizeError(BLOCK_MESSAGE)

        indexed = []
        for generation, objects in reader.xref.items():
            if type(generation) is not int or generation < 0:
                raise PDFEmbeddedObjectSizeError(BLOCK_MESSAGE)
            for number, offset in objects.items():
                if number == 0:
                    continue
                if (type(number) is not int or type(offset) is not int or
                        number < 1 or not 0 < offset < len(contents)):
                    raise PDFEmbeddedObjectSizeError(BLOCK_MESSAGE)
                indexed.append((number, generation))
                if len(indexed) > MAX_OBJECTS:
                    raise PDFEmbeddedObjectSizeError(BLOCK_MESSAGE)

        streams = {}
        for number, generation in indexed:
            obj = reader.get_object(IndirectObject(number, generation, reader))
            if not isinstance(obj, StreamObject):
                continue
            if type(obj._data) is not bytes:
                raise PDFEmbeddedObjectSizeError(BLOCK_MESSAGE)
            streams[id(obj)] = obj
            if len(streams) > MAX_STREAMS:
                raise PDFEmbeddedObjectSizeError(BLOCK_MESSAGE)

        specs = _specifications(reader, MAX_ATTACHMENTS)
        embedded = {}
        for spec in specs:
            if not isinstance(spec, DictionaryObject) or "/EF" not in spec:
                raise PDFEmbeddedObjectSizeError(BLOCK_MESSAGE)
            ef = _resolve(spec.raw_get("/EF"))
            if not isinstance(ef, DictionaryObject):
                raise PDFEmbeddedObjectSizeError(BLOCK_MESSAGE)
            # Both file specification variants must be inspected. They may
            # refer to different streams, neither of which can be ignored.
            refs = [ef.raw_get(key) for key in ("/F", "/UF") if key in ef]
            if not refs:
                raise PDFEmbeddedObjectSizeError(BLOCK_MESSAGE)
            for ref in refs:
                obj = _resolve(ref)
                if not isinstance(obj, StreamObject):
                    raise PDFEmbeddedObjectSizeError(BLOCK_MESSAGE)
                embedded[id(obj)] = obj
                streams[id(obj)] = obj
                if len(streams) > MAX_STREAMS:
                    raise PDFEmbeddedObjectSizeError(BLOCK_MESSAGE)

        # Orphan /Type /EmbeddedFile streams are also embedded objects even
        # when no FileSpec points to them.
        for key, stream in streams.items():
            if stream.get("/Type") == "/EmbeddedFile":
                embedded[key] = stream

        large_encoded = sum(len(stream._data) > LARGE_ENCODED_BYTES
                            for stream in streams.values())
        large_decoded = high_ratio = large_declared = 0
        for stream in embedded.values():
            decoded, compressed = _embedded_size(stream, StreamObject)
            raw_length = len(stream._data)
            large_decoded += decoded > LARGE_DECODED_BYTES
            high_ratio += bool(compressed and decoded > raw_length * HIGH_EXPANSION_RATIO)
            params = stream.get("/Params")
            if params is not None:
                params = _resolve(params)
                if not isinstance(params, DictionaryObject):
                    raise PDFEmbeddedObjectSizeError(BLOCK_MESSAGE)
                if "/Size" in params:
                    declared = _resolve(params.raw_get("/Size"))
                    if not isinstance(declared, int) or isinstance(declared, bool) or declared < 0:
                        raise PDFEmbeddedObjectSizeError(BLOCK_MESSAGE)
                    large_declared += declared > LARGE_DECLARED_BYTES

        return PDFEmbeddedObjectSizes(
            len(streams), len(embedded), large_encoded,
            large_decoded, high_ratio, large_declared,
        )
    except PDFEmbeddedObjectSizeError:
        raise
    except Exception:
        # Parser diagnostics may contain untrusted filenames or private bytes.
        raise PDFEmbeddedObjectSizeError(BLOCK_MESSAGE) from None
