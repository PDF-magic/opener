"""Inspect PDF indirect-object and page-tree relationships (opener-0284).

This is an optional Enhanced protection building block, not an active scan
stage. It relies on the maintained strict parser from opener-0283 and cannot
approve opening, clean-cache reuse, quarantine removal or a profile selection.
"""

from dataclasses import dataclass
from io import BytesIO
import re

from pdf_structure_parser import (MAX_STRUCTURE_INPUT_BYTES, MAX_STRUCTURE_PAGES,
                                  PDFStructureParseError, parse_pdf_structure)

MAX_RELATIONSHIP_OBJECTS = 4096
MAX_RELATIONSHIP_EDGES = 65536
MAX_RELATIONSHIP_DEPTH = 64
_ERROR = "PDF object relationships could not be verified; opening was stopped."
_UNSUPPORTED = "PDF object relationships require unsupported inspection; opening was stopped."


class PDFObjectRelationshipError(RuntimeError):
    """Fixed, path-free failure without PDF content or document paths."""


@dataclass(frozen=True)
class PDFObjectRelationships:
    object_count: int
    reference_count: int
    page_count: int
    # This stage never authorizes a clean scan or launching a file.
    permits_open: bool = False


def inspect_pdf_object_relationships(contents: bytes) -> PDFObjectRelationships:
    """Verify indirect links, generations, and page-tree parent/child edges.

    A strict parser must already have accepted the document. Support is
    intentionally bounded; unsupported object streams or excessive graphs
    are rejected, not assumed valid. Ordinary /Parent back-links are allowed.
    """
    if type(contents) is not bytes or not contents or len(contents) > MAX_STRUCTURE_INPUT_BYTES:
        raise PDFObjectRelationshipError(_UNSUPPORTED)
    if not re.match(rb"\A%PDF-(1\.[0-7]|2\.0)[\r\n]", contents[:9]) or b"%%EOF" not in contents[-1024:]:
        raise PDFObjectRelationshipError(_ERROR)

    try:
        from pypdf import PdfReader
        from pypdf.generic import ArrayObject, DictionaryObject, IndirectObject
        reader = PdfReader(BytesIO(contents), strict=True)
        if reader.is_encrypted or reader.xref_objStm:
            raise PDFObjectRelationshipError(_UNSUPPORTED)

        active = {}
        for generation, records in reader.xref.items():
            for number, offset in records.items():
                if number == 0:
                    continue
                if (type(number) is not int or type(generation) is not int or
                        type(offset) is not int or number < 1 or
                        not 0 <= generation <= 65535 or offset <= 0):
                    raise PDFObjectRelationshipError(_ERROR)
                key = (number, generation)
                if key in active:
                    raise PDFObjectRelationshipError(_ERROR)
                active[key] = IndirectObject(number, generation, reader)
        if not active or len(active) > MAX_RELATIONSHIP_OBJECTS:
            raise PDFObjectRelationshipError(_UNSUPPORTED)

        def key(reference):
            if type(reference) is not IndirectObject or reference.pdf is not reader:
                raise PDFObjectRelationshipError(_ERROR)
            identity = (reference.idnum, reference.generation)
            if identity not in active:
                raise PDFObjectRelationshipError(_ERROR)
            return identity

        objects = {}
        for identity, reference in active.items():
            obj = reader.get_object(reference)
            if obj is None:
                raise PDFObjectRelationshipError(_ERROR)
            objects[identity] = obj

        edges = 0
        for obj in (*objects.values(), reader.trailer):
            stack = [(obj, 0)]
            while stack:
                node, depth = stack.pop()
                if depth > MAX_RELATIONSHIP_DEPTH:
                    raise PDFObjectRelationshipError(_UNSUPPORTED)
                if type(node) is IndirectObject:
                    key(node)
                    edges += 1
                    if edges > MAX_RELATIONSHIP_EDGES:
                        raise PDFObjectRelationshipError(_UNSUPPORTED)
                elif isinstance(node, DictionaryObject):
                    stack.extend((value, depth + 1) for value in node.values())
                elif isinstance(node, ArrayObject):
                    stack.extend((value, depth + 1) for value in node)

        root_ref = reader.trailer.raw_get("/Root")
        root = objects[key(root_ref)]
        if not isinstance(root, DictionaryObject) or root.raw_get("/Type") != "/Catalog":
            raise PDFObjectRelationshipError(_ERROR)
        pages_ref = root.raw_get("/Pages")
        visited = set()

        def pages_in(reference, expected_parent, depth):
            if depth > MAX_RELATIONSHIP_DEPTH:
                raise PDFObjectRelationshipError(_UNSUPPORTED)
            identity = key(reference)
            if identity in visited:
                raise PDFObjectRelationshipError(_ERROR)
            visited.add(identity)
            entry = objects[identity]
            if not isinstance(entry, DictionaryObject):
                raise PDFObjectRelationshipError(_ERROR)
            if expected_parent is None:
                if "/Parent" in entry:
                    raise PDFObjectRelationshipError(_ERROR)
            elif "/Parent" not in entry or key(entry.raw_get("/Parent")) != expected_parent:
                raise PDFObjectRelationshipError(_ERROR)
            kind = entry.raw_get("/Type")
            if kind == "/Page":
                return 1
            if kind != "/Pages":
                raise PDFObjectRelationshipError(_ERROR)
            kids = entry.raw_get("/Kids")
            count = entry.raw_get("/Count")
            if (not isinstance(kids, ArrayObject) or
                    not isinstance(count, int) or type(count) is bool or count < 0):
                raise PDFObjectRelationshipError(_ERROR)
            actual = sum(pages_in(child, identity, depth + 1) for child in kids)
            if actual != count:
                raise PDFObjectRelationshipError(_ERROR)
            return actual

        count = pages_in(pages_ref, None, 0)
        if count < 1 or count > MAX_STRUCTURE_PAGES:
            raise PDFObjectRelationshipError(_UNSUPPORTED)
        # Only after checking the acyclic page tree do we invoke the shared
        # parser's page traversal; cyclic malformed Kids must not hang it.
        structure = parse_pdf_structure(contents)
        if count != structure.page_count:
            raise PDFObjectRelationshipError(_ERROR)
        return PDFObjectRelationships(len(active), edges, count)
    except PDFObjectRelationshipError:
        raise
    except PDFStructureParseError:
        raise PDFObjectRelationshipError(_ERROR) from None
    except Exception:
        # Never expose parser errors, private PDF strings or filesystem paths.
        raise PDFObjectRelationshipError(_ERROR) from None
