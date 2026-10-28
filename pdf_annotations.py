"""Passive, bounded PDF annotation inspection for a future Enhanced stage.

The result is evidence, never a clean verdict or authorization to open a PDF.
Annotation action payloads, appearances, and embedded files require separate
inspection; this module never decodes, follows, or executes those contents.
"""

from dataclasses import dataclass
from io import BytesIO
from math import isfinite
from types import MappingProxyType

MAX_PDF_BYTES = 16 * 1024 * 1024
MAX_PAGES = 1024
MAX_INDIRECT_OBJECTS = 4096
MAX_ANNOTATIONS = 2048
MAX_APPEARANCE_STATES = 64
MAX_ADDITIONAL_ACTIONS = 32
BLOCK_MESSAGE = "PDF annotations could not be fully inspected; opening was stopped."

# PDF 2.0 annotation kinds, plus established legacy/extension kinds. Unknown
# subtypes are not silently labeled safe; a future Enhanced stage must reject
# them until it explicitly supports their semantics.
ANNOTATION_KINDS = MappingProxyType({
    "/Text": "text", "/Link": "link", "/FreeText": "free_text",
    "/Line": "line", "/Square": "square", "/Circle": "circle",
    "/Polygon": "polygon", "/PolyLine": "polyline",
    "/Highlight": "highlight", "/Underline": "underline",
    "/Squiggly": "squiggly", "/StrikeOut": "strikeout",
    "/Stamp": "stamp", "/Caret": "caret", "/Ink": "ink",
    "/Popup": "popup", "/FileAttachment": "file_attachment",
    "/Sound": "sound", "/Movie": "movie", "/Widget": "widget",
    "/Screen": "screen", "/PrinterMark": "printer_mark",
    "/TrapNet": "trap_net", "/Watermark": "watermark",
    "/3D": "3d", "/Redact": "redact", "/RichMedia": "rich_media",
    "/Projection": "projection",
})
ACTIVE_KINDS = frozenset({
    "file_attachment", "sound", "movie", "widget", "screen", "3d",
    "rich_media", "projection",
})


class PDFAnnotationInspectionError(RuntimeError):
    """Fixed, path-free failure for incomplete or unsupported inspection."""


@dataclass(frozen=True)
class PDFAnnotationInspection:
    annotation_count: int
    annotation_kinds: tuple[str, ...]
    direct_action_count: int
    additional_action_annotations: int
    destination_count: int
    appearance_count: int
    active_annotation_count: int
    permits_open: bool = False

    def __post_init__(self):
        counts = (self.annotation_count, self.direct_action_count,
                  self.additional_action_annotations, self.destination_count,
                  self.appearance_count, self.active_annotation_count)
        if (any(type(value) is not int or not 0 <= value <= MAX_ANNOTATIONS
                for value in counts) or
                any(value > self.annotation_count for value in counts[1:]) or
                type(self.annotation_kinds) is not tuple or
                self.annotation_kinds != tuple(sorted(set(self.annotation_kinds))) or
                any(kind not in ANNOTATION_KINDS.values()
                    for kind in self.annotation_kinds) or
                bool(self.annotation_count) != bool(self.annotation_kinds) or
                self.permits_open is not False):
            raise ValueError("Annotation findings cannot authorize opening")

    @property
    def needs_further_inspection(self) -> bool:
        return bool(self.annotation_count)


def inspect_pdf_annotations(contents: bytes) -> PDFAnnotationInspection:
    """Classify every page /Annots entry without evaluating untrusted payloads.

    The page tree, annotation dictionaries and immediate interactive pointers
    are checked. Action bodies, appearance streams and file contents are not
    deemed clean by this result: later independent Enhanced checks own them.
    """
    if (type(contents) is not bytes or not contents or
            len(contents) > MAX_PDF_BYTES or
            not contents.startswith(b"%PDF-") or
            not contents.rstrip().endswith(b"%%EOF")):
        raise PDFAnnotationInspectionError(BLOCK_MESSAGE)
    try:
        from pypdf import PdfReader
        from pypdf.generic import (
            ArrayObject, ByteStringObject, DictionaryObject, FloatObject,
            IndirectObject, NameObject, NumberObject, StreamObject,
            TextStringObject,
        )
    except (ImportError, OSError) as exc:
        raise PDFAnnotationInspectionError(BLOCK_MESSAGE) from exc

    try:
        reader = PdfReader(BytesIO(contents), strict=True)
        pages = reader.pages
        if (reader.is_encrypted or reader.xref_objStm or
                not 0 < len(pages) <= MAX_PAGES or
                sum(len(offsets) for offsets in reader.xref.values()) >
                MAX_INDIRECT_OBJECTS):
            raise PDFAnnotationInspectionError(BLOCK_MESSAGE)

        def resolve(value):
            visited = set()
            while isinstance(value, IndirectObject):
                key = (value.idnum, value.generation)
                if key in visited or len(visited) >= MAX_INDIRECT_OBJECTS:
                    raise PDFAnnotationInspectionError(BLOCK_MESSAGE)
                visited.add(key)
                value = value.get_object()
            return value

        def dictionary(value):
            value = resolve(value)
            if not isinstance(value, DictionaryObject):
                raise PDFAnnotationInspectionError(BLOCK_MESSAGE)
            return value

        def check_action(value):
            action = dictionary(value)
            if ("/S" not in action or
                    not isinstance(resolve(action.raw_get("/S")), NameObject)):
                raise PDFAnnotationInspectionError(BLOCK_MESSAGE)

        def check_appearance(value):
            appearance = dictionary(value)
            if not appearance or any(key not in ("/N", "/R", "/D")
                                     for key in appearance.keys()):
                raise PDFAnnotationInspectionError(BLOCK_MESSAGE)
            for entry in appearance.values():
                entry = resolve(entry)
                if isinstance(entry, StreamObject):
                    continue  # Do not decode untrusted drawing streams.
                if (not isinstance(entry, DictionaryObject) or
                        not 0 < len(entry) <= MAX_APPEARANCE_STATES):
                    raise PDFAnnotationInspectionError(BLOCK_MESSAGE)
                for state in entry.values():
                    if not isinstance(resolve(state), StreamObject):
                        raise PDFAnnotationInspectionError(BLOCK_MESSAGE)

        kinds = set()
        action_count = extra_count = dest_count = appearance_count = active = total = 0
        seen_refs = set()
        for page in pages:
            if "/Annots" not in page:
                continue
            annotations = resolve(page.raw_get("/Annots"))
            if not isinstance(annotations, ArrayObject):
                raise PDFAnnotationInspectionError(BLOCK_MESSAGE)
            if total + len(annotations) > MAX_ANNOTATIONS:
                raise PDFAnnotationInspectionError(BLOCK_MESSAGE)
            for ref in annotations:
                # The same annotation must not appear twice or belong to two
                # different pages; fail rather than silently undercount it.
                annotation = dictionary(ref)
                identity = ((ref.idnum, ref.generation) if
                            isinstance(ref, IndirectObject) else id(annotation))
                if identity in seen_refs:
                    raise PDFAnnotationInspectionError(BLOCK_MESSAGE)
                seen_refs.add(identity)
                total += 1
                if ("/Subtype" not in annotation or
                        "/Rect" not in annotation):
                    raise PDFAnnotationInspectionError(BLOCK_MESSAGE)
                subtype = resolve(annotation.raw_get("/Subtype"))
                if not isinstance(subtype, NameObject) or subtype not in ANNOTATION_KINDS:
                    raise PDFAnnotationInspectionError(BLOCK_MESSAGE)
                kind = ANNOTATION_KINDS[subtype]
                kinds.add(kind)
                rectangle = resolve(annotation.raw_get("/Rect"))
                if (not isinstance(rectangle, ArrayObject) or len(rectangle) != 4 or
                        any(not isinstance(resolve(coord),
                                           (NumberObject, FloatObject)) or
                            not isfinite(float(resolve(coord)))
                            for coord in rectangle)):
                    raise PDFAnnotationInspectionError(BLOCK_MESSAGE)
                if "/F" in annotation:
                    flags = resolve(annotation.raw_get("/F"))
                    if (not isinstance(flags, NumberObject) or
                            not 0 <= int(flags) <= 0xffffffff):
                        raise PDFAnnotationInspectionError(BLOCK_MESSAGE)
                if "/A" in annotation:
                    check_action(annotation.raw_get("/A"))
                    action_count += 1
                if "/AA" in annotation:
                    triggers = dictionary(annotation.raw_get("/AA"))
                    if not 0 < len(triggers) <= MAX_ADDITIONAL_ACTIONS:
                        raise PDFAnnotationInspectionError(BLOCK_MESSAGE)
                    for trigger, value in triggers.items():
                        if not isinstance(trigger, NameObject):
                            raise PDFAnnotationInspectionError(BLOCK_MESSAGE)
                        check_action(value)
                    extra_count += 1
                if "/Dest" in annotation:
                    dest = resolve(annotation.raw_get("/Dest"))
                    if not isinstance(dest, (ArrayObject, NameObject,
                                             TextStringObject, ByteStringObject)):
                        raise PDFAnnotationInspectionError(BLOCK_MESSAGE)
                    dest_count += 1
                if "/AP" in annotation:
                    check_appearance(annotation.raw_get("/AP"))
                    appearance_count += 1
                if kind == "file_attachment":
                    if "/FS" not in annotation:
                        raise PDFAnnotationInspectionError(BLOCK_MESSAGE)
                    dictionary(annotation.raw_get("/FS"))
                if (kind in ACTIVE_KINDS or "/A" in annotation or
                        "/AA" in annotation or "/Dest" in annotation):
                    active += 1

        return PDFAnnotationInspection(
            total, tuple(sorted(kinds)), action_count, extra_count,
            dest_count, appearance_count, active,
        )
    except PDFAnnotationInspectionError:
        raise
    except Exception as exc:
        raise PDFAnnotationInspectionError(BLOCK_MESSAGE) from exc
