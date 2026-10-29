"""Inventory PDF features outside the current bounded structural analyzer.

This is passive feature evidence only. It does not decode page content or
attachments, execute actions, verify signatures, produce a clean verdict, or
authorize opening. The installed ClamAV scan gate remains independent.
"""
from dataclasses import dataclass, field
from enum import Enum
from io import BytesIO
import re

from pdf_structure_parser import (
    MAX_STRUCTURE_INPUT_BYTES, PDFStructureParseError, parse_pdf_structure,
)

MAX_INDEXED_OBJECTS = 4096
MAX_GRAPH_NODES = 65536
MAX_INDIRECT_RESOLUTIONS = 32768
MAX_GRAPH_DEPTH = 64
_ERROR = "PDF feature support could not be fully inspected; opening was stopped."
_FINAL_STARTXREF = re.compile(
    rb"startxref[ \t\r\n]+([0-9]{1,16})[ \t\r\n]+%%EOF[ \t\r\n]*\Z"
)
_OBJECT_HEADER = re.compile(rb"[0-9]+[ \t\r\n]+[0-9]+[ \t\r\n]+obj\b")
_XREF_STREAM_TYPE = re.compile(rb"/Type[ \t\r\n]*/XRef\b")
_ACTION_NAMES = frozenset((
    "/GoTo", "/GoToR", "/GoToE", "/Launch", "/Thread", "/URI", "/Sound",
    "/Movie", "/Hide", "/Named", "/SubmitForm", "/ResetForm", "/ImportData",
    "/JavaScript", "/SetOCGState", "/Rendition", "/Trans", "/GoTo3DView",
    "/RichMediaExecute",
))
_EXTERNAL_ACTIONS = frozenset(("/GoToR", "/GoToE", "/Launch", "/URI"))
_FORM_ACTIONS = frozenset(("/SubmitForm", "/ResetForm", "/ImportData"))
_MEDIA_ACTIONS = frozenset(("/Movie", "/Sound", "/Rendition", "/GoTo3DView",
                            "/RichMediaExecute"))


class UnsupportedPDFFeature(str, Enum):
    """Stable identifiers for known PDF features not fully covered here."""

    ENCRYPTED_DOCUMENT = "encryptedDocument"
    CROSS_REFERENCE_STREAM = "crossReferenceStream"
    OBJECT_STREAM = "objectStream"
    INCREMENTAL_REVISIONS = "incrementalRevisions"
    UNSUPPORTED_STREAM_FILTER = "unsupportedStreamFilter"
    UNSUPPORTED_FILTER_PARAMETERS = "unsupportedFilterParameters"
    PAGE_CONTENT_STREAMS = "pageContentStreams"
    ANNOTATIONS = "annotations"
    INTERACTIVE_FORMS = "interactiveForms"
    JAVASCRIPT = "javascript"
    ACTIONS = "actions"
    EXTERNAL_ACTIONS = "externalActions"
    FORM_ACTIONS = "formActions"
    UNKNOWN_ACTION_TYPE = "unknownActionType"
    EMBEDDED_FILES = "embeddedFiles"
    XFA_FORMS = "xfaForms"
    RICH_MEDIA = "richMedia"
    THREE_DIMENSIONAL_CONTENT = "threeDimensionalContent"
    DIGITAL_SIGNATURES = "digitalSignatures"
    PDF_PORTFOLIO = "pdfPortfolio"
    OPTIONAL_CONTENT_LAYERS = "optionalContentLayers"
    TAGGED_STRUCTURE = "taggedStructure"


class PDFUnsupportedFeatureInspectionError(RuntimeError):
    """Fixed, path-free failure instead of an incomplete or false-empty report."""


@dataclass(frozen=True)
class PDFUnsupportedFeatureReport:
    """Immutable, fixed-code inventory; this report never authorizes opening."""

    feature_codes: tuple[UnsupportedPDFFeature, ...]
    inspected_object_count: int
    inspection_complete: bool
    authorizes_open: bool = field(default=False, init=False)

    def __post_init__(self):
        if (
            type(self.feature_codes) is not tuple
            or any(type(item) is not UnsupportedPDFFeature for item in self.feature_codes)
            or self.feature_codes != tuple(sorted(
                set(self.feature_codes), key=lambda item: item.value
            ))
            or type(self.inspected_object_count) is not int
            or not 0 <= self.inspected_object_count <= MAX_INDEXED_OBJECTS
            or type(self.inspection_complete) is not bool
            or self.inspection_complete != (not bool(self.feature_codes))
            or self.authorizes_open is not False
        ):
            raise ValueError("Invalid unsupported-feature evidence")

    @property
    def has_unsupported_features(self) -> bool:
        return bool(self.feature_codes)

    def to_dict(self) -> dict:
        """Return fixed identifiers only; never expose PDF strings or paths."""
        return {
            "schemaVersion": 1,
            "featureCodes": [item.value for item in self.feature_codes],
            "inspectedObjectCount": self.inspected_object_count,
            "inspectionComplete": self.inspection_complete,
            "authorizesOpen": False,
        }


def _report(features, object_count=0):
    codes = tuple(sorted(set(features), key=lambda item: item.value))
    return PDFUnsupportedFeatureReport(
        feature_codes=codes,
        inspected_object_count=object_count,
        inspection_complete=not bool(codes),
    )


def inspect_pdf_unsupported_features(contents: bytes) -> PDFUnsupportedFeatureReport:
    """Identify known constructs this structural analyzer cannot fully inspect.

    The walk is bounded and follows only validated, indexed indirect objects.
    It never decodes stream payloads or supplies passwords. Unsupported
    cross-reference streams are identified from their final startxref target
    before PdfReader is constructed; encrypted and object-stream PDFs return
    explicit incomplete reports rather than falsely claiming features absent.
    """
    if (type(contents) is not bytes or not 0 < len(contents) <= MAX_STRUCTURE_INPUT_BYTES
            or not contents.startswith(b"%PDF-")):
        raise PDFUnsupportedFeatureInspectionError(_ERROR)

    match = _FINAL_STARTXREF.search(contents[-2048:])
    if match is None:
        raise PDFUnsupportedFeatureInspectionError(_ERROR)
    xref_offset = int(match.group(1))
    if not 0 < xref_offset < len(contents):
        raise PDFUnsupportedFeatureInspectionError(_ERROR)

    target = contents[xref_offset:xref_offset + 128]
    if not (target.startswith(b"xref") and
            (len(target) == 4 or target[4:5] in b" \t\r\n")):
        # Avoid constructing a reader that could decompress an xref stream.
        if (_OBJECT_HEADER.match(target) is not None and
                _XREF_STREAM_TYPE.search(contents[xref_offset:xref_offset + 8192])):
            return _report((UnsupportedPDFFeature.CROSS_REFERENCE_STREAM,))
        raise PDFUnsupportedFeatureInspectionError(_ERROR)

    try:
        from pypdf import PdfReader
        from pypdf.generic import (
            ArrayObject, DictionaryObject, IndirectObject, NameObject, StreamObject,
        )
    except (ImportError, OSError):
        raise PDFUnsupportedFeatureInspectionError(_ERROR) from None

    try:
        reader = PdfReader(BytesIO(contents), strict=True)
        if reader.is_encrypted:
            return _report((UnsupportedPDFFeature.ENCRYPTED_DOCUMENT,))
        if reader.xref_objStm:
            return _report((UnsupportedPDFFeature.OBJECT_STREAM,))

        # Keep this analyzer aligned with the shared strict framing, stream
        # length, catalog and page-tree validation before inventorying objects.
        try:
            parse_pdf_structure(contents)
        except PDFStructureParseError:
            raise PDFUnsupportedFeatureInspectionError(_ERROR) from None

        active = set()
        for generation, entries in reader.xref.items():
            if type(generation) is not int or not 0 <= generation <= 65535:
                raise PDFUnsupportedFeatureInspectionError(_ERROR)
            for number, offset in entries.items():
                if number == 0:
                    continue
                if (type(number) is not int or type(offset) is not int
                        or not 1 <= number <= 2**31 - 1
                        or not 0 < offset < len(contents)):
                    raise PDFUnsupportedFeatureInspectionError(_ERROR)
                active.add((number, generation))
                if len(active) > MAX_INDEXED_OBJECTS:
                    raise PDFUnsupportedFeatureInspectionError(_ERROR)
        if not active:
            raise PDFUnsupportedFeatureInspectionError(_ERROR)

        features = set()
        visited_refs = set()
        visited_direct = set()
        node_count = 0
        resolution_count = 0

        def resolve(value):
            nonlocal resolution_count
            chain = set()
            while isinstance(value, IndirectObject):
                key = (value.idnum, value.generation)
                if key not in active or key in chain:
                    raise PDFUnsupportedFeatureInspectionError(_ERROR)
                chain.add(key)
                resolution_count += 1
                if resolution_count > MAX_INDIRECT_RESOLUTIONS:
                    raise PDFUnsupportedFeatureInspectionError(_ERROR)
                value = value.get_object()
                if value is None:
                    raise PDFUnsupportedFeatureInspectionError(_ERROR)
            return value

        def name_at(obj, key):
            if key not in obj:
                return None
            value = resolve(obj.raw_get(key))
            return str(value) if isinstance(value, NameObject) else None

        def inspect_dictionary(obj, context):
            kind = name_at(obj, "/Type")
            subtype = name_at(obj, "/Subtype")
            action = name_at(obj, "/S")
            field_type = name_at(obj, "/FT")

            if kind == "/Page":
                if "/Contents" in obj:
                    features.add(UnsupportedPDFFeature.PAGE_CONTENT_STREAMS)
                if "/Annots" in obj:
                    features.add(UnsupportedPDFFeature.ANNOTATIONS)
            if "/AcroForm" in obj or field_type is not None:
                features.add(UnsupportedPDFFeature.INTERACTIVE_FORMS)
            if "/XFA" in obj:
                features.add(UnsupportedPDFFeature.XFA_FORMS)
            if ("/EmbeddedFiles" in obj or "/EmbeddedFile" in obj or "/EF" in obj
                    or "/AF" in obj or subtype == "/FileAttachment"
                    or kind == "/Filespec"):
                features.add(UnsupportedPDFFeature.EMBEDDED_FILES)
            if ("/RichMedia" in obj or "/RichMediaContent" in obj
                    or "/RichMediaSettings" in obj or subtype in
                    ("/RichMedia", "/Movie", "/Sound", "/Screen", "/Projection")):
                features.add(UnsupportedPDFFeature.RICH_MEDIA)
            if (kind in ("/3D", "/3DView") or
                    any(key in obj for key in ("/3D", "/3DD", "/3DV", "/3DView"))):
                features.add(UnsupportedPDFFeature.THREE_DIMENSIONAL_CONTENT)
            if "/Collection" in obj or kind == "/Collection":
                features.add(UnsupportedPDFFeature.PDF_PORTFOLIO)
            if any(key in obj for key in
                   ("/OCProperties", "/OC", "/OCG", "/OCMD")):
                features.add(UnsupportedPDFFeature.OPTIONAL_CONTENT_LAYERS)
            if any(key in obj for key in
                   ("/StructTreeRoot", "/StructElem", "/MarkInfo", "/RoleMap")):
                features.add(UnsupportedPDFFeature.TAGGED_STRUCTURE)
            if (kind == "/Sig" or field_type == "/Sig" or "/ByteRange" in obj
                    or any(key in obj for key in ("/DocMDP", "/UR", "/UR3"))):
                features.add(UnsupportedPDFFeature.DIGITAL_SIGNATURES)
            if "/Prev" in obj:
                features.add(UnsupportedPDFFeature.INCREMENTAL_REVISIONS)

            if "/JS" in obj or action == "/JavaScript":
                features.add(UnsupportedPDFFeature.JAVASCRIPT)
                features.add(UnsupportedPDFFeature.ACTIONS)
            if ("/A" in obj or "/AA" in obj or "/OpenAction" in obj or "/Next" in obj
                    or action in _ACTION_NAMES):
                features.add(UnsupportedPDFFeature.ACTIONS)
            if action in _EXTERNAL_ACTIONS:
                features.add(UnsupportedPDFFeature.EXTERNAL_ACTIONS)
            if action in _FORM_ACTIONS:
                features.add(UnsupportedPDFFeature.FORM_ACTIONS)
            if action in _MEDIA_ACTIONS:
                features.add(UnsupportedPDFFeature.RICH_MEDIA)
            if action is not None and (context == "action" or kind == "/Action"):
                if action not in _ACTION_NAMES:
                    features.add(UnsupportedPDFFeature.UNKNOWN_ACTION_TYPE)

            if isinstance(obj, StreamObject):
                if kind == "/ObjStm":
                    features.add(UnsupportedPDFFeature.OBJECT_STREAM)
                if kind == "/XRef":
                    features.add(UnsupportedPDFFeature.CROSS_REFERENCE_STREAM)
                if "/Filter" in obj:
                    filter_value = resolve(obj.raw_get("/Filter"))
                    if not (isinstance(filter_value, NameObject)
                            and str(filter_value) == "/FlateDecode"):
                        features.add(UnsupportedPDFFeature.UNSUPPORTED_STREAM_FILTER)
                if "/DecodeParms" in obj:
                    features.add(UnsupportedPDFFeature.UNSUPPORTED_FILTER_PARAMETERS)

        def visit(value, depth=0, context=""):
            nonlocal node_count
            if depth > MAX_GRAPH_DEPTH:
                raise PDFUnsupportedFeatureInspectionError(_ERROR)
            if isinstance(value, IndirectObject):
                key = (value.idnum, value.generation)
                if key not in active:
                    raise PDFUnsupportedFeatureInspectionError(_ERROR)
                if key in visited_refs:
                    return
                visited_refs.add(key)
                value = resolve(value)
            else:
                marker = id(value)
                if isinstance(value, (DictionaryObject, ArrayObject)):
                    if marker in visited_direct:
                        return
                    visited_direct.add(marker)

            node_count += 1
            if node_count > MAX_GRAPH_NODES:
                raise PDFUnsupportedFeatureInspectionError(_ERROR)
            if isinstance(value, DictionaryObject):
                inspect_dictionary(value, context)
                for key, child in value.items():
                    child_context = ("action" if key in (
                        NameObject("/A"), NameObject("/AA"),
                        NameObject("/OpenAction"), NameObject("/Next"),
                    ) else "")
                    visit(child, depth + 1, child_context)
            elif isinstance(value, ArrayObject):
                for child in value:
                    visit(child, depth + 1, context)

        visit(reader.trailer)
        # Include orphaned indexed objects that are not reachable from /Root.
        for number, generation in sorted(active):
            if (number, generation) not in visited_refs:
                visit(IndirectObject(number, generation, reader))
        return _report(features, len(visited_refs))
    except PDFUnsupportedFeatureInspectionError:
        raise
    except Exception:
        # Never leak parser diagnostics, PDF-controlled strings, or file paths.
        raise PDFUnsupportedFeatureInspectionError(_ERROR) from None
