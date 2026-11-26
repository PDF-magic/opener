"""Detect PDF XFA form entries without parsing or executing their payloads.

This optional Enhanced inspection returns bounded, path-free evidence only.
It never decodes XFA/XML streams, invokes scripts, changes profile settings,
or grants permission to launch a document. The installed ClamAV gate remains
independent and mandatory.
"""

from dataclasses import dataclass, field
from io import BytesIO

from pdf_structure_parser import PDFStructureParseError, parse_pdf_structure


MAX_XFA_PACKETS = 64
MAX_XFA_PACKET_NAME_LENGTH = 128
MAX_XFA_REFERENCES = 256
_FAILURE = "PDF XFA forms could not be fully inspected; opening was stopped."


class PDFXFAInspectionError(RuntimeError):
    """A fixed, content-free failure when XFA presence cannot be verified."""


@dataclass(frozen=True)
class PDFXFAInspection:
    """Validated, immutable XFA presence evidence, never an opening verdict."""

    representation: str
    packet_count: int
    permits_open: bool = field(default=False, init=False)

    def __post_init__(self):
        if (type(self.representation) is not str or
                self.representation not in ("none", "stream", "packets") or
                type(self.packet_count) is not int or
                (self.representation in ("none", "stream") and self.packet_count != 0) or
                (self.representation == "packets" and
                 not 1 <= self.packet_count <= MAX_XFA_PACKETS) or
                self.permits_open is not False):
            raise ValueError("Invalid XFA inspection metadata")

    @property
    def contains_xfa(self) -> bool:
        return self.representation != "none"

    def to_dict(self) -> dict[str, str | int | bool]:
        """Return a detached record containing no PDF-controlled strings."""
        return {
            "schemaVersion": 1,
            "containsXFA": self.contains_xfa,
            "representation": self.representation,
            "packetCount": self.packet_count,
            "authorizesOpen": False,
        }


def inspect_pdf_xfa_forms(contents: bytes) -> PDFXFAInspection:
    """Inspect the catalog's /AcroForm /XFA entry using strict PDF parsing.

    Valid PDF XFA representations are a single stream or an array alternating
    packet-name strings with streams. Resolve indirect references with a
    bounded loop, but never read, decode, parse, or return XFA/XML bytes.
    Missing XFA in a valid PDF is distinct from malformed/uninspectable XFA.
    """
    try:
        parse_pdf_structure(contents)
    except PDFStructureParseError:
        raise PDFXFAInspectionError(_FAILURE) from None

    try:
        from pypdf import PdfReader
        from pypdf.generic import (
            ArrayObject, ByteStringObject, DictionaryObject, IndirectObject,
            StreamObject, TextStringObject,
        )
    except (ImportError, OSError):
        raise PDFXFAInspectionError(_FAILURE) from None

    try:
        reader = PdfReader(BytesIO(contents), strict=True)
        root = reader.trailer["/Root"]
        if not isinstance(root, DictionaryObject) or isinstance(root, StreamObject):
            raise PDFXFAInspectionError(_FAILURE)

        reference_count = 0

        def resolve(value):
            nonlocal reference_count
            visited = set()
            while isinstance(value, IndirectObject):
                key = (value.idnum, value.generation)
                if key in visited:
                    raise PDFXFAInspectionError(_FAILURE)
                visited.add(key)
                reference_count += 1
                if reference_count > MAX_XFA_REFERENCES:
                    raise PDFXFAInspectionError(_FAILURE)
                value = value.get_object()
            return value

        if "/AcroForm" not in root:
            return PDFXFAInspection("none", 0)
        form = resolve(root.raw_get("/AcroForm"))
        if not isinstance(form, DictionaryObject) or isinstance(form, StreamObject):
            raise PDFXFAInspectionError(_FAILURE)
        if "/XFA" not in form:
            return PDFXFAInspection("none", 0)

        xfa = resolve(form.raw_get("/XFA"))
        if isinstance(xfa, StreamObject):
            return PDFXFAInspection("stream", 0)
        if not isinstance(xfa, ArrayObject) or not 2 <= len(xfa) <= MAX_XFA_PACKETS * 2 or len(xfa) % 2:
            raise PDFXFAInspectionError(_FAILURE)

        for index in range(0, len(xfa), 2):
            name = resolve(xfa[index])
            packet = resolve(xfa[index + 1])
            if (not isinstance(name, (TextStringObject, ByteStringObject)) or
                    not 0 < len(name) <= MAX_XFA_PACKET_NAME_LENGTH or
                    not isinstance(packet, StreamObject)):
                raise PDFXFAInspectionError(_FAILURE)

        return PDFXFAInspection("packets", len(xfa) // 2)
    except PDFXFAInspectionError:
        raise
    except Exception:
        # pypdf exceptions may include untrusted PDF text or source paths.
        raise PDFXFAInspectionError(_FAILURE) from None
