"""Classify declared and magic-byte types of PDF embedded attachments.

Passive optional Enhanced evidence only. Reuses the existing bounded
attachment discovery and decoding code; never invokes ClamAV, writes extracted
files, executes attachments or authorizes opening the containing PDF.
"""

from dataclasses import dataclass, field
from io import BytesIO

from enhanced_embedded_files import _extract, _resolve, _specifications
from pdf_structure_parser import PDFStructureParseError, parse_pdf_structure


MAX_ATTACHMENTS = 32
MAX_ATTACHMENT_BYTES = 4 * 1024 * 1024
MAX_TOTAL_BYTES = 16 * 1024 * 1024
MAX_NAME_LENGTH = 512
MAX_MIME_LENGTH = 128
_FAILURE = "Embedded PDF file types could not be fully inspected; opening was stopped."

_KINDS = frozenset((
    "pdf", "png", "jpeg", "gif", "zip", "ole", "elf", "pe_or_dos",
    "mach_o", "wasm", "java_or_fat_binary", "script", "html", "xml",
    "rtf", "text", "unknown_binary",
))
_EXECUTABLES = frozenset(("elf", "pe_or_dos", "mach_o", "wasm",
                          "java_or_fat_binary", "script"))
_MIME_KIND = {
    "application/pdf": "pdf",
    "image/png": "png",
    "image/jpeg": "jpeg",
    "image/gif": "gif",
    "application/zip": "zip",
    "application/x-zip-compressed": "zip",
    "application/msword": "ole",
    "application/x-ole-storage": "ole",
    "application/x-msdownload": "pe_or_dos",
    "application/x-executable": "elf",
    "application/wasm": "wasm",
    "text/plain": "text",
    "text/html": "html",
    "application/xhtml+xml": "html",
    "text/xml": "xml",
    "application/xml": "xml",
    "application/rtf": "rtf",
    "text/rtf": "rtf",
}
_EXTENSION_KIND = {
    "pdf": "pdf", "png": "png", "jpg": "jpeg", "jpeg": "jpeg",
    "gif": "gif", "zip": "zip", "docx": "zip", "xlsx": "zip",
    "pptx": "zip", "odt": "zip", "doc": "ole", "xls": "ole",
    "ppt": "ole", "exe": "pe_or_dos", "dll": "pe_or_dos",
    "elf": "elf", "wasm": "wasm", "class": "java_or_fat_binary",
    "sh": "script", "html": "html", "htm": "html", "xml": "xml",
    "rtf": "rtf", "txt": "text", "csv": "text",
}


class PDFEmbeddedFileTypeError(RuntimeError):
    """Fixed error, never containing attachment names, bytes or paths."""


@dataclass(frozen=True)
class PDFEmbeddedFileTypes:
    """Aggregated fixed-type evidence, deliberately excluding all file names."""

    attachment_count: int
    inspected_bytes: int
    detected_kinds: tuple[str, ...]
    unknown_count: int
    executable_count: int
    declaration_mismatch_count: int
    extension_mismatch_count: int
    authorizes_open: bool = field(default=False, init=False)

    def __post_init__(self):
        counts = (
            self.attachment_count, self.inspected_bytes, self.unknown_count,
            self.executable_count, self.declaration_mismatch_count,
            self.extension_mismatch_count,
        )
        if (any(type(number) is not int or number < 0 for number in counts)
                or self.attachment_count > MAX_ATTACHMENTS
                or self.inspected_bytes > MAX_TOTAL_BYTES
                or any(number > self.attachment_count for number in counts[2:])
                or type(self.detected_kinds) is not tuple
                or self.detected_kinds != tuple(sorted(set(self.detected_kinds)))
                or any(type(kind) is not str or kind not in _KINDS
                       for kind in self.detected_kinds)
                or (self.attachment_count == 0) != (not self.detected_kinds)
                or (self.unknown_count > 0) != ("unknown_binary" in self.detected_kinds)
                or (self.executable_count > 0) != bool(
                    _EXECUTABLES.intersection(self.detected_kinds))
                or self.authorizes_open is not False):
            raise ValueError("Invalid embedded-file type evidence")

    def to_dict(self) -> dict:
        """Produce detached, fixed-category JSON data only."""
        return {
            "schemaVersion": 1,
            "attachmentCount": self.attachment_count,
            "inspectedBytes": self.inspected_bytes,
            "detectedKinds": list(self.detected_kinds),
            "unknownTypeCount": self.unknown_count,
            "executableCount": self.executable_count,
            "declaredTypeMismatchCount": self.declaration_mismatch_count,
            "extensionMismatchCount": self.extension_mismatch_count,
            "authorizesOpen": False,
        }


def _sniff(payload: bytes) -> str:
    """Use bytes, never extensions or claimed MIME as the inferred type."""
    if payload.startswith(b"%PDF-"):
        return "pdf"
    if payload.startswith(b"\x89PNG\r\n\x1a\n"):
        return "png"
    if payload.startswith(b"\xff\xd8\xff"):
        return "jpeg"
    if payload.startswith((b"GIF87a", b"GIF89a")):
        return "gif"
    if payload.startswith((b"PK\x03\x04", b"PK\x05\x06", b"PK\x07\x08")):
        return "zip"
    if payload.startswith(b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1"):
        return "ole"
    if payload.startswith(b"\x7fELF"):
        return "elf"
    if payload.startswith(b"MZ"):
        return "pe_or_dos"
    if payload[:4] in (b"\xfe\xed\xfa\xce", b"\xce\xfa\xed\xfe",
                       b"\xfe\xed\xfa\xcf", b"\xcf\xfa\xed\xfe"):
        return "mach_o"
    if payload[:4] in (b"\xca\xfe\xba\xbe", b"\xbe\xba\xfe\xca"):
        # Java class and fat Mach-O share a prefix: do not falsely distinguish.
        return "java_or_fat_binary"
    if payload.startswith(b"\x00asm"):
        return "wasm"
    if payload.startswith((b"#!", b"\xef\xbb\xbf#!")):
        return "script"
    stripped = payload[:512].lstrip(b" \t\r\n")
    if stripped[:15].lower().startswith(b"<!doctype html") or (
        stripped[:5].lower() == b"<html"
    ):
        return "html"
    if stripped.startswith((b"<?xml", b"\xef\xbb\xbf<?xml")):
        return "xml"
    if stripped.startswith(b"{\\rtf"):
        return "rtf"
    # A conservative text signature: valid UTF-8, without binary controls.
    try:
        sample = payload[:4096].decode("utf-8")
    except UnicodeDecodeError:
        return "unknown_binary"
    if sample and not any(
        ord(char) < 32 and char not in "\n\r\t" or ord(char) == 127
        for char in sample
    ):
        return "text"
    return "unknown_binary"


def _declared_kind(stream) -> str | None:
    from pypdf.generic import NameObject

    subtype = stream.get("/Subtype")
    if subtype is None:
        return None
    if not isinstance(subtype, NameObject):
        raise PDFEmbeddedFileTypeError(_FAILURE)
    name = str(subtype)
    if len(name) > MAX_MIME_LENGTH or not name.startswith("/"):
        raise PDFEmbeddedFileTypeError(_FAILURE)
    # PDF Name escaping permits '#2F' for a slash in MIME names.
    mime = name[1:].replace("#2F", "/").replace("#2f", "/").lower()
    return _MIME_KIND.get(mime)


def _extension_kind(spec) -> str | None:
    from pypdf.generic import ByteStringObject, TextStringObject

    for key in ("/UF", "/F"):
        if key not in spec:
            continue
        name = _resolve(spec.raw_get(key))
        if (not isinstance(name, TextStringObject)
                or isinstance(name, ByteStringObject)
                or len(name) > MAX_NAME_LENGTH):
            raise PDFEmbeddedFileTypeError(_FAILURE)
        # Only a fixed, lowercased extension escapes this function.
        name = str(name).replace("\\", "/").rsplit("/", 1)[-1]
        return _EXTENSION_KIND.get(name.rsplit(".", 1)[-1].lower()) if "." in name else None
    return None


def inspect_pdf_embedded_file_types(contents: bytes) -> PDFEmbeddedFileTypes:
    """Inspect every discoverable PDF embedded file without external access.

    Unknown signatures are reported, not interpreted as a clean file type.
    A mismatch is informational evidence, not a malware verdict. Detection
    errors fail closed; absence of anomalies never permits opening.
    """
    try:
        parse_pdf_structure(contents)
    except PDFStructureParseError:
        raise PDFEmbeddedFileTypeError(_FAILURE) from None
    try:
        from pypdf import PdfReader
        from pypdf.generic import DictionaryObject, StreamObject
    except (ImportError, OSError):
        raise PDFEmbeddedFileTypeError(_FAILURE) from None
    try:
        reader = PdfReader(BytesIO(contents), strict=True)
        if reader.is_encrypted:
            raise PDFEmbeddedFileTypeError(_FAILURE)
        specifications = _specifications(reader, MAX_ATTACHMENTS)
        kinds = set()
        count = unknown = executable = declaration_mismatches = extension_mismatches = 0
        total = 0
        for spec in specifications:
            if not isinstance(spec, DictionaryObject):
                raise PDFEmbeddedFileTypeError(_FAILURE)
            ef = _resolve(spec.get("/EF"))
            if not isinstance(ef, DictionaryObject):
                raise PDFEmbeddedFileTypeError(_FAILURE)
            stream = _resolve(ef.get("/UF", ef.get("/F")))
            if not isinstance(stream, StreamObject):
                raise PDFEmbeddedFileTypeError(_FAILURE)
            # Reuse the established raw/Flate-only bounded attachment decoder.
            payload = _extract(spec, MAX_ATTACHMENT_BYTES)
            total += len(payload)
            if total > MAX_TOTAL_BYTES:
                raise PDFEmbeddedFileTypeError(_FAILURE)
            kind = _sniff(payload)
            kinds.add(kind)
            count += 1
            unknown += kind == "unknown_binary"
            executable += kind in _EXECUTABLES
            hint = _declared_kind(stream)
            suffix = _extension_kind(spec)
            declaration_mismatches += hint is not None and kind != hint
            extension_mismatches += suffix is not None and kind != suffix
        return PDFEmbeddedFileTypes(
            count, total, tuple(sorted(kinds)), unknown, executable,
            declaration_mismatches, extension_mismatches,
        )
    except PDFEmbeddedFileTypeError:
        raise
    except Exception:
        # Both pypdf and attachment-reader exceptions may contain source text.
        raise PDFEmbeddedFileTypeError(_FAILURE) from None
