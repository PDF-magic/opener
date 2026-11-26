"""Extract bounded declared PDF /Info and XMP metadata without opening files.

This optional Enhanced-stage inspector operates on immutable PDF bytes. It does
not inspect metadata for truth, log document-controlled values, execute content,
or authorize PDF opening; all deployed ClamAV safeguards remain independent.
"""

from dataclasses import dataclass, field
from io import BytesIO
import re
import xml.etree.ElementTree as ET
import zlib

from pdf_structure_parser import PDFStructureParseError, parse_pdf_structure


MAX_METADATA_TEXT = 1024
MAX_XMP_BYTES = 128 * 1024
MAX_XML_NODES = 1024
MAX_XML_DEPTH = 32
MAX_INDIRECT_REFERENCES = 32
MAX_XML_CREATORS = 8
_ERROR = "PDF declared metadata could not be fully extracted; opening was stopped."

# Expose only known metadata keys, never PDF-provided arbitrary dictionary keys.
_INFO_KEYS = {
    "/Title": "title",
    "/Author": "author",
    "/Subject": "subject",
    "/Keywords": "keywords",
    "/Creator": "creator",
    "/Producer": "producer",
    "/CreationDate": "creationDate",
    "/ModDate": "modificationDate",
    "/Trapped": "trapped",
}
_XMP_NAMESPACES = {
    "dc": "http://purl.org/dc/elements/1.1/",
    "pdf": "http://ns.adobe.com/pdf/1.3/",
    "xmp": "http://ns.adobe.com/xap/1.0/",
    "rdf": "http://www.w3.org/1999/02/22-rdf-syntax-ns#",
}
_XMP_KEYS = {
    ("dc", "title"): "title",
    ("dc", "creator"): "author",
    ("dc", "description"): "subject",
    ("dc", "subject"): "keywords",
    ("pdf", "Keywords"): "keywords",
    ("pdf", "Producer"): "producer",
    ("xmp", "CreatorTool"): "creator",
    ("xmp", "CreateDate"): "creationDate",
    ("xmp", "ModifyDate"): "modificationDate",
}
_ALLOWED_FIELDS = frozenset(_INFO_KEYS.values())
_XMP_TAGS = {
    f"{{{_XMP_NAMESPACES[namespace]}}}{key}": result
    for (namespace, key), result in _XMP_KEYS.items()
}
_RDF_LI = f"{{{_XMP_NAMESPACES['rdf']}}}li"
_RDF_RDF = f"{{{_XMP_NAMESPACES['rdf']}}}RDF"
_XMP_META = "{adobe:ns:meta/}xmpmeta"


class PDFDeclaredMetadataError(RuntimeError):
    """A fixed, content-free failure instead of a partial metadata result."""


def _safe_text(value):
    if type(value) is not str or len(value) > MAX_METADATA_TEXT:
        raise PDFDeclaredMetadataError(_ERROR)
    if any(ord(char) < 32 or 127 <= ord(char) < 160 for char in value):
        raise PDFDeclaredMetadataError(_ERROR)
    return value.strip()


def _fields_are_valid(fields):
    return (
        type(fields) is tuple
        and len(fields) <= len(_ALLOWED_FIELDS)
        and all(
            type(item) is tuple and len(item) == 2
            and type(item[0]) is str and item[0] in _ALLOWED_FIELDS
            and type(item[1]) is str and bool(item[1])
            and len(item[1]) <= MAX_METADATA_TEXT
            and not any(ord(c) < 32 or 127 <= ord(c) < 160 for c in item[1])
            for item in fields
        )
        and tuple(sorted(fields)) == fields
        and len({name for name, _ in fields}) == len(fields)
    )


@dataclass(frozen=True)
class PDFDeclaredMetadata:
    """In-memory metadata values are deliberately excluded from default repr."""

    info_fields: tuple[tuple[str, str], ...] = field(repr=False)
    xmp_fields: tuple[tuple[str, str], ...] = field(repr=False)
    has_xmp_stream: bool
    authorizes_open: bool = field(default=False, init=False)

    def __post_init__(self):
        if (not _fields_are_valid(self.info_fields)
                or not _fields_are_valid(self.xmp_fields)
                or type(self.has_xmp_stream) is not bool
                or (not self.has_xmp_stream and bool(self.xmp_fields))
                or self.authorizes_open is not False):
            raise ValueError("Invalid declared PDF metadata evidence")

    def to_dict(self):
        """Explicitly opt into a detached, JSON-compatible copy of private values."""
        return {
            "schemaVersion": 1,
            "info": dict(self.info_fields),
            "xmp": dict(self.xmp_fields),
            "hasXMP": self.has_xmp_stream,
            "authorizesOpen": False,
        }


def _xmp_fields(xml_bytes):
    if (not xml_bytes or len(xml_bytes) > MAX_XMP_BYTES
            or b"\x00" in xml_bytes
            or re.search(rb"<!\s*(?:DOCTYPE|ENTITY)\b", xml_bytes, re.I)):
        raise PDFDeclaredMetadataError(_ERROR)

    text = xml_bytes.decode("utf-8-sig")
    root = ET.fromstring(text)
    if root.tag not in (_RDF_RDF, _XMP_META):
        raise PDFDeclaredMetadataError(_ERROR)
    if root.tag == _XMP_META and not any(child.tag == _RDF_RDF for child in root):
        raise PDFDeclaredMetadataError(_ERROR)

    extracted = {}
    stack = [(root, 1)]
    nodes = 0
    while stack:
        node, depth = stack.pop()
        nodes += 1
        if nodes > MAX_XML_NODES or depth > MAX_XML_DEPTH:
            raise PDFDeclaredMetadataError(_ERROR)
        stack.extend((child, depth + 1) for child in node)
        if node.tag in _XMP_TAGS:
            values = [li.text for li in node.iter(_RDF_LI) if li.text]
            if len(values) > MAX_XML_CREATORS:
                raise PDFDeclaredMetadataError(_ERROR)
            candidate = "; ".join(values) if values else (node.text or "")
            candidate = _safe_text(candidate)
            if candidate:
                extracted.setdefault(_XMP_TAGS[node.tag], candidate)
        # XMP may encode properties as rdf:Description attributes.
        if node.tag == f"{{{_XMP_NAMESPACES['rdf']}}}Description":
            for key, value in node.attrib.items():
                if key in _XMP_TAGS:
                    candidate = _safe_text(value)
                    if candidate:
                        extracted.setdefault(_XMP_TAGS[key], candidate)
    return tuple(sorted(extracted.items()))


def _decode_xmp_stream(stream):
    from pypdf.generic import ArrayObject, NameObject

    payload = stream._data
    if type(payload) is not bytes or len(payload) > MAX_XMP_BYTES:
        raise PDFDeclaredMetadataError(_ERROR)
    filters = stream.get("/Filter")
    if filters is None:
        decoded = payload
    elif (isinstance(filters, NameObject) and filters == "/FlateDecode"
          and stream.get("/DecodeParms") is None):
        decompressor = zlib.decompressobj()
        decoded = decompressor.decompress(payload, MAX_XMP_BYTES + 1)
        if (len(decoded) > MAX_XMP_BYTES or not decompressor.eof
                or decompressor.unused_data or decompressor.unconsumed_tail):
            raise PDFDeclaredMetadataError(_ERROR)
        decoded += decompressor.flush(MAX_XMP_BYTES + 1 - len(decoded))
    else:
        # Unsupported encodings must not silently yield an empty XMP result.
        raise PDFDeclaredMetadataError(_ERROR)
    if len(decoded) > MAX_XMP_BYTES:
        raise PDFDeclaredMetadataError(_ERROR)
    return decoded


def extract_pdf_declared_metadata(contents: bytes) -> PDFDeclaredMetadata:
    """Extract conventional Info fields and supported XMP RDF properties.

    Unknown PDF metadata keys are ignored; unsupported or malformed *declared*
    structures fail closed. No metadata is written to disk or automatically
    logged. A caller that intentionally serializes the result is responsible
    for handling the sensitive author/title/document strings.
    """
    try:
        parse_pdf_structure(contents)
    except PDFStructureParseError:
        raise PDFDeclaredMetadataError(_ERROR) from None

    try:
        from pypdf import PdfReader
        from pypdf.generic import (
            ByteStringObject, DictionaryObject, IndirectObject,
            NameObject, StreamObject, TextStringObject,
        )
    except (ImportError, OSError):
        raise PDFDeclaredMetadataError(_ERROR) from None

    try:
        reader = PdfReader(BytesIO(contents), strict=True)
        references = 0

        def resolve(value):
            nonlocal references
            seen = set()
            while isinstance(value, IndirectObject):
                key = (value.idnum, value.generation)
                if key in seen:
                    raise PDFDeclaredMetadataError(_ERROR)
                seen.add(key)
                references += 1
                if references > MAX_INDIRECT_REFERENCES:
                    raise PDFDeclaredMetadataError(_ERROR)
                value = value.get_object()
            return value

        info = {}
        if "/Info" in reader.trailer:
            dictionary = resolve(reader.trailer.raw_get("/Info"))
            if not isinstance(dictionary, DictionaryObject) or isinstance(
                dictionary, StreamObject
            ):
                raise PDFDeclaredMetadataError(_ERROR)
            for pdf_key, field_name in _INFO_KEYS.items():
                if pdf_key not in dictionary:
                    continue
                value = resolve(dictionary.raw_get(pdf_key))
                if pdf_key == "/Trapped":
                    if not isinstance(value, NameObject) or value not in (
                        "/True", "/False", "/Unknown"
                    ):
                        raise PDFDeclaredMetadataError(_ERROR)
                    safe = str(value)[1:].lower()
                else:
                    # Undecodable PDF byte strings cannot be represented as
                    # reliable document metadata. Refuse rather than guess.
                    if isinstance(value, ByteStringObject) or not isinstance(
                        value, TextStringObject
                    ):
                        raise PDFDeclaredMetadataError(_ERROR)
                    safe = _safe_text(str(value))
                if safe:
                    info[field_name] = safe

        xmp = ()
        present = False
        root = resolve(reader.trailer.raw_get("/Root"))
        if not isinstance(root, DictionaryObject) or isinstance(root, StreamObject):
            raise PDFDeclaredMetadataError(_ERROR)
        if "/Metadata" in root:
            present = True
            stream = resolve(root.raw_get("/Metadata"))
            if not isinstance(stream, StreamObject):
                raise PDFDeclaredMetadataError(_ERROR)
            if (stream.get("/Type") != "/Metadata" or
                    stream.get("/Subtype") != "/XML"):
                raise PDFDeclaredMetadataError(_ERROR)
            xmp = _xmp_fields(_decode_xmp_stream(stream))

        return PDFDeclaredMetadata(tuple(sorted(info.items())), xmp, present)
    except PDFDeclaredMetadataError:
        raise
    except Exception:
        # Exception text from XML and PDF parsers may include private document
        # content or paths. Do not expose the underlying exception.
        raise PDFDeclaredMetadataError(_ERROR) from None
