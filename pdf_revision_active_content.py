"""Detect active PDF content in superseded incremental revisions, without execution.

An optional Enhanced-only, read-only inspector. Parse each validated historical
snapshot before its objects can be hidden by later xref replacements. Do not
execute scripts, unpack streams, open paths or treat results as scan clearance.
"""
from dataclasses import dataclass
from io import BytesIO
import re

from pdf_incremental_revisions import (
    MAX_PDF_BYTES, _END, _OBJECT, _read_xref, inspect_pdf_incremental_revisions,
)

MAX_REVISIONS = 16
MAX_OBJECTS = 8192
MAX_GRAPH_NODES = 65536
MAX_ACTIVE_OBJECTS = 512
BLOCK_MESSAGE = "Historical PDF active content could not be fully inspected; opening was stopped."
_HISTORICAL_EOF = re.compile(
    rb"(?:\A|[\r\n])startxref[ \t\r\n]+([0-9]{1,16})[ \t\r\n]+%%EOF(?:\r\n|\r|\n)?"
)
_CATEGORIES = frozenset((
    "javascript", "external_action", "form_action", "multimedia",
    "attachment", "automatic_action",
))
_ACTIONS = {
    "/JavaScript": "javascript", "/Launch": "external_action",
    "/URI": "external_action", "/GoToR": "external_action",
    "/GoToE": "external_action", "/SubmitForm": "form_action",
    "/ResetForm": "form_action", "/ImportData": "form_action",
    "/Rendition": "multimedia", "/RichMediaExecute": "multimedia",
    "/Movie": "multimedia", "/Sound": "multimedia",
    "/GoTo3DView": "multimedia",
}
_MEDIA_SUBTYPES = frozenset((
    "/RichMedia", "/Movie", "/Sound", "/Screen", "/3D", "/Projection",
))


class PDFHistoricalActiveContentError(RuntimeError):
    """Incomplete historical inspection is always a fixed non-clean error."""


@dataclass(frozen=True)
class PDFHistoricalActiveContent:
    revision_count: int
    historical_active_object_count: int
    hidden_active_object_count: int
    hidden_categories: tuple[str, ...]
    permits_open: bool = False

    def __post_init__(self):
        if (type(self.revision_count) is not int or
                not 1 <= self.revision_count <= MAX_REVISIONS or
                any(type(value) is not int or not 0 <= value <= MAX_ACTIVE_OBJECTS
                    for value in (self.historical_active_object_count,
                                  self.hidden_active_object_count)) or
                self.hidden_active_object_count > self.historical_active_object_count or
                type(self.hidden_categories) is not tuple or
                self.hidden_categories != tuple(sorted(set(self.hidden_categories))) or
                any(item not in _CATEGORIES for item in self.hidden_categories) or
                bool(self.hidden_active_object_count) != bool(self.hidden_categories) or
                self.permits_open is not False):
            raise ValueError("Historical PDF evidence cannot authorize opening")

    @property
    def has_hidden_active_content(self):
        return self.hidden_active_object_count > 0


def _markers(obj, dictionary_type):
    """Inspect trusted PDF name keys only, never scripts, media or string text."""
    if not isinstance(obj, dictionary_type):
        return set()
    result = set()
    kind = obj.get("/S")
    if kind in _ACTIONS:
        result.add(_ACTIONS[kind])
    if "/JS" in obj:
        result.add("javascript")
    if "/AA" in obj:
        result.add("automatic_action")
    if obj.get("/Subtype") in _MEDIA_SUBTYPES or any(
        name in obj for name in ("/RichMediaContent", "/RichMediaSettings", "/Assets")
    ):
        result.add("multimedia")
    if obj.get("/Subtype") == "/FileAttachment" or any(
        name in obj for name in ("/EmbeddedFiles", "/EF", "/AF")
    ):
        result.add("attachment")
    if "/XFA" in obj:
        result.add("form_action")
    return result


def inspect_pdf_revision_active_content(contents: bytes) -> PDFHistoricalActiveContent:
    """Flag active historical objects whose exact xref location is now superseded.

    Validate the existing /Prev chain, open each older complete PDF snapshot,
    then walk indexed objects including orphans and nested direct dictionaries.
    Compare (number, generation, physical offset), not just object IDs: a newer
    revision can replace an unsafe object with an innocuous one of the same ID.
    """
    if type(contents) is not bytes or not 0 < len(contents) <= MAX_PDF_BYTES:
        raise PDFHistoricalActiveContentError(BLOCK_MESSAGE)
    try:
        from pypdf import PdfReader
        from pypdf.generic import ArrayObject, DictionaryObject, IndirectObject
        chain = inspect_pdf_incremental_revisions(contents)
        if chain.revision_count > MAX_REVISIONS:
            raise PDFHistoricalActiveContentError(BLOCK_MESSAGE)
        latest = PdfReader(BytesIO(contents), strict=True)
        if latest.is_encrypted or latest.xref_objStm:
            raise PDFHistoricalActiveContentError(BLOCK_MESSAGE)
        total_objects = 0
        total_nodes = 0

        def indexed_objects(reader, snapshot):
            nonlocal total_objects
            found = {}
            for generation, offsets in reader.xref.items():
                if type(generation) is not int or not 0 <= generation <= 65535:
                    raise PDFHistoricalActiveContentError(BLOCK_MESSAGE)
                for number, offset in offsets.items():
                    if number == 0:
                        continue
                    if (type(number) is not int or type(offset) is not int or
                            number < 1 or not 0 < offset < len(snapshot)):
                        raise PDFHistoricalActiveContentError(BLOCK_MESSAGE)
                    header = _OBJECT.match(snapshot, offset)
                    if (header is None or int(header.group(1)) != number or
                            int(header.group(2)) != generation):
                        raise PDFHistoricalActiveContentError(BLOCK_MESSAGE)
                    total_objects += 1
                    if total_objects > MAX_OBJECTS:
                        raise PDFHistoricalActiveContentError(BLOCK_MESSAGE)
                    found[(number, generation, offset)] = (number, generation)
            return found

        latest_locations = set(indexed_objects(latest, contents))
        if chain.revision_count == 1:
            return PDFHistoricalActiveContent(1, 0, 0, ())

        # The already-validated chain is followed again to recover exact
        # historical EOF boundaries. A duplicate marker is ambiguous, not safe.
        previous = int(_END.search(contents).group(1))
        bounds = []
        seen_offsets = set()
        current_limit = len(contents)
        while True:
            if previous in seen_offsets or len(seen_offsets) >= MAX_REVISIONS:
                raise PDFHistoricalActiveContentError(BLOCK_MESSAGE)
            seen_offsets.add(previous)
            _, older, _ = _read_xref(contents, previous, latest)
            if older is None:
                break
            matches = [m for m in _HISTORICAL_EOF.finditer(contents[:previous])
                       if int(m.group(1)) == older and m.end() < current_limit]
            if len(matches) != 1:
                raise PDFHistoricalActiveContentError(BLOCK_MESSAGE)
            boundary = matches[0].end()
            if boundary <= older or boundary >= current_limit:
                raise PDFHistoricalActiveContentError(BLOCK_MESSAGE)
            bounds.append(boundary)
            current_limit = boundary
            previous = older
        if len(bounds) != chain.revision_count - 1:
            raise PDFHistoricalActiveContentError(BLOCK_MESSAGE)

        historical_active = {}
        for boundary in bounds:
            snapshot = contents[:boundary]
            reader = PdfReader(BytesIO(snapshot), strict=True)
            if reader.is_encrypted or reader.xref_objStm:
                raise PDFHistoricalActiveContentError(BLOCK_MESSAGE)
            for location, (number, generation) in indexed_objects(reader, snapshot).items():
                # A shared location is identical across snapshots; inspect once.
                if location in historical_active:
                    continue
                obj = reader.get_object(IndirectObject(number, generation, reader))
                if obj is None:
                    raise PDFHistoricalActiveContentError(BLOCK_MESSAGE)
                stack = [obj]
                visited = set()
                categories = set()
                while stack:
                    item = stack.pop()
                    total_nodes += 1
                    if total_nodes > MAX_GRAPH_NODES:
                        raise PDFHistoricalActiveContentError(BLOCK_MESSAGE)
                    if not isinstance(item, (DictionaryObject, ArrayObject)):
                        continue
                    if id(item) in visited:
                        continue
                    visited.add(id(item))
                    if isinstance(item, DictionaryObject):
                        categories.update(_markers(item, DictionaryObject))
                        stack.extend(item.raw_get(k) for k in item.keys()
                                     if not isinstance(item.raw_get(k), IndirectObject))
                    else:
                        stack.extend(child for child in item
                                     if not isinstance(child, IndirectObject))
                if categories:
                    historical_active[location] = categories
                    if len(historical_active) > MAX_ACTIVE_OBJECTS:
                        raise PDFHistoricalActiveContentError(BLOCK_MESSAGE)

        hidden = [found for location, found in historical_active.items()
                  if location not in latest_locations]
        categories = tuple(sorted(set().union(*hidden))) if hidden else ()
        return PDFHistoricalActiveContent(
            chain.revision_count, len(historical_active), len(hidden), categories,
        )
    except PDFHistoricalActiveContentError:
        raise
    except Exception as exc:
        # Temporary synthetic-fixture CI diagnostic; remove before merge.
        raise PDFHistoricalActiveContentError(BLOCK_MESSAGE) from exc
