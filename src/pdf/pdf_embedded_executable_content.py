"""Passive detection of executable signatures in PDF stream objects.

A future Enhanced stage may consume this evidence, but this module never
executes content, grants opening, or changes the installed ClamAV scan gate.
"""

from dataclasses import dataclass
from io import BytesIO
import zlib

MAX_PDF_BYTES = 16 * 1024 * 1024
MAX_PAGES = 1024
MAX_INDIRECT_OBJECTS = 4096
MAX_STREAMS = 1024
MAX_STREAM_BYTES = 4 * 1024 * 1024
MAX_TOTAL_STREAM_BYTES = 16 * 1024 * 1024
BLOCK_MESSAGE = "Embedded PDF executable content could not be fully inspected; opening was stopped."
KINDS = frozenset({"dos_executable", "elf", "java_or_fat_binary", "mach_o",
                   "pe", "script", "wasm"})


class PDFEmbeddedExecutableInspectionError(RuntimeError):
    """Fixed, path-free outcome for incomplete inspection."""


@dataclass(frozen=True)
class PDFEmbeddedExecutableInspection:
    inspected_stream_count: int
    executable_count: int
    executable_kinds: tuple[str, ...]
    permits_open: bool = False

    def __post_init__(self):
        if (type(self.inspected_stream_count) is not int or
                not 0 <= self.inspected_stream_count <= MAX_STREAMS or
                type(self.executable_count) is not int or
                not 0 <= self.executable_count <= self.inspected_stream_count or
                type(self.executable_kinds) is not tuple or
                self.executable_kinds != tuple(sorted(set(self.executable_kinds))) or
                any(kind not in KINDS for kind in self.executable_kinds) or
                bool(self.executable_count) != bool(self.executable_kinds) or
                self.permits_open is not False):
            raise ValueError("Executable inspection cannot authorize PDF opening")

    @property
    def has_executables(self) -> bool:
        return self.executable_count != 0


def _classify(data):
    """Only identify byte signatures, never infer safety from file names."""
    if data.startswith(b"MZ"):
        if len(data) >= 64:
            offset = int.from_bytes(data[60:64], "little")
            if 0 < offset <= len(data) - 4 and data[offset:offset + 4] == b"PE\0\0":
                return "pe"
        return "dos_executable"
    if data.startswith(b"\x7fELF"):
        return "elf"
    if data[:4] in (b"\xfe\xed\xfa\xce", b"\xce\xfa\xed\xfe",
                    b"\xfe\xed\xfa\xcf", b"\xcf\xfa\xed\xfe"):
        return "mach_o"
    if data[:4] in (b"\xca\xfe\xba\xbe", b"\xbe\xba\xfe\xca"):
        # Java bytecode and universal Mach-O share a four-byte prefix.
        return "java_or_fat_binary"
    if data.startswith(b"\0asm"):
        return "wasm"
    if data.startswith((b"#!", b"\xef\xbb\xbf#!")):
        return "script"
    return None


def _decode(stream, per_stream_limit):
    """Only raw or single FlateDecode streams; never unbounded get_data()."""
    raw = stream._data
    if type(raw) is not bytes or len(raw) > per_stream_limit:
        raise PDFEmbeddedExecutableInspectionError(BLOCK_MESSAGE)
    filter_name = stream.get("/Filter")
    if filter_name is None:
        data = raw
    elif filter_name == "/FlateDecode" and stream.get("/DecodeParms") is None:
        try:
            inflater = zlib.decompressobj()
            data = inflater.decompress(raw, per_stream_limit + 1)
            if (len(data) > per_stream_limit or not inflater.eof or
                    inflater.unconsumed_tail or inflater.unused_data):
                raise PDFEmbeddedExecutableInspectionError(BLOCK_MESSAGE)
        except zlib.error as exc:
            raise PDFEmbeddedExecutableInspectionError(BLOCK_MESSAGE) from exc
    else:
        # Opaque filters cannot be treated as absence of embedded executables.
        raise PDFEmbeddedExecutableInspectionError(BLOCK_MESSAGE)
    return data


def inspect_pdf_embedded_executable_content(contents: bytes) -> PDFEmbeddedExecutableInspection:
    """Inspect every indexed PDF stream, including orphaned/unlisted streams.

    This is metadata only. An executable-free result is NOT a clean PDF verdict.
    Encrypted, malformed, unsupported, or over-budget PDFs fail closed.
    """
    if type(contents) is not bytes or not contents or len(contents) > MAX_PDF_BYTES:
        raise PDFEmbeddedExecutableInspectionError(BLOCK_MESSAGE)
    try:
        from pypdf import PdfReader
        from pypdf.generic import IndirectObject, StreamObject
    except (ImportError, OSError) as exc:
        raise PDFEmbeddedExecutableInspectionError(BLOCK_MESSAGE) from exc

    try:
        reader = PdfReader(BytesIO(contents), strict=True)
        if reader.is_encrypted or reader.xref_objStm or len(reader.pages) > MAX_PAGES:
            raise PDFEmbeddedExecutableInspectionError(BLOCK_MESSAGE)
        count, total, detected = 0, 0, []
        indexed = 0
        for generation, offsets in reader.xref.items():
            if type(generation) is not int or not 0 <= generation <= 65535:
                raise PDFEmbeddedExecutableInspectionError(BLOCK_MESSAGE)
            for number, offset in offsets.items():
                if number == 0:
                    continue
                if (type(number) is not int or type(offset) is not int or
                        number < 1 or offset <= 0):
                    raise PDFEmbeddedExecutableInspectionError(BLOCK_MESSAGE)
                indexed += 1
                if indexed > MAX_INDIRECT_OBJECTS:
                    raise PDFEmbeddedExecutableInspectionError(BLOCK_MESSAGE)
                obj = IndirectObject(number, generation, reader).get_object()
                if obj is None:
                    raise PDFEmbeddedExecutableInspectionError(BLOCK_MESSAGE)
                if not isinstance(obj, StreamObject):
                    continue
                count += 1
                if count > MAX_STREAMS:
                    raise PDFEmbeddedExecutableInspectionError(BLOCK_MESSAGE)
                data = _decode(obj, MAX_STREAM_BYTES)
                total += len(data)
                if total > MAX_TOTAL_STREAM_BYTES:
                    raise PDFEmbeddedExecutableInspectionError(BLOCK_MESSAGE)
                kind = _classify(data)
                if kind is not None:
                    detected.append(kind)
        return PDFEmbeddedExecutableInspection(
            count, len(detected), tuple(sorted(set(detected)))
        )
    except PDFEmbeddedExecutableInspectionError:
        raise
    except Exception as exc:
        raise PDFEmbeddedExecutableInspectionError(BLOCK_MESSAGE) from exc
