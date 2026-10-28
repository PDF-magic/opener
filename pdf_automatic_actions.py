"""Inspect automatic PDF actions without evaluating document-supplied content.

This is passive Enhanced-protection evidence, NOT an open authorization.
Only immutable in-memory bytes are accepted. It uses the maintained strict
structure parser from opener-0283 and never decodes JavaScript or page streams.
A future sandboxed Enhanced pipeline must enforce execution time/memory limits
and use these findings without bypassing the installed ClamAV scan gate.
"""

from dataclasses import dataclass
from io import BytesIO

from pdf_structure_parser import parse_pdf_structure, PDFStructureParseError


MAX_ACTIONS = 512
MAX_REFERENCES = 4096
MAX_TREE_NODES = 256
MAX_FIELDS = 512
MAX_ANNOTATIONS = 2048
MAX_ACTION_DEPTH = 64

_ERROR = "PDF automatic actions could not be fully inspected; opening was stopped."
_DEPENDENCY = "The PDF automatic action inspector is unavailable; opening was stopped."

# Stable identifiers deliberately exclude untrusted script text and filenames.
_KNOWN_ACTIONS = frozenset((
    "/GoTo", "/GoToR", "/GoToE", "/Launch", "/Thread", "/URI", "/Sound",
    "/Movie", "/Hide", "/Named", "/SubmitForm", "/ResetForm", "/ImportData",
    "/JavaScript", "/SetOCGState", "/Rendition", "/Trans", "/GoTo3DView",
    "/RichMediaExecute",
))


class PDFAutomaticActionError(RuntimeError):
    """Fail-closed, path-free indication of incomplete action inspection."""


@dataclass(frozen=True)
class PDFAutomaticActionInspection:
    """Bounded action findings only; never a clean verdict or open permission."""

    action_count: int
    open_destination_count: int
    trigger_types: tuple[str, ...]
    action_types: tuple[str, ...]
    permits_open: bool = False

    @property
    def has_automatic_actions(self) -> bool:
        return bool(self.action_count or self.open_destination_count)


def inspect_pdf_automatic_actions(
    contents: bytes, *, _javascript_inspector=None,
) -> PDFAutomaticActionInspection:
    """Inspect catalog, page, annotation, field and name-tree auto-action hooks.

    Never interpret /JS stream/string payloads or follow URI/Launch destinations.
    A named /OpenAction destination is counted but NOT treated as JavaScript.
    Unresolved links, malformed action dictionaries and exceeded limits fail
    closed instead of falsely reporting that no automatic actions exist.
    """
    try:
        parse_pdf_structure(contents)
    except PDFStructureParseError as error:
        raise PDFAutomaticActionError(str(error)) from None

    try:
        from pypdf import PdfReader
        from pypdf.generic import (
            ArrayObject, ByteStringObject, DictionaryObject, IndirectObject,
            NameObject, NullObject, TextStringObject, StreamObject,
        )
    except (ImportError, OSError):
        raise PDFAutomaticActionError(_DEPENDENCY) from None

    try:
        reader = PdfReader(BytesIO(contents), strict=True)
        root = reader.trailer["/Root"]
        if not isinstance(root, DictionaryObject):
            raise PDFAutomaticActionError(_ERROR)

        reference_count = 0
        action_count = 0
        open_destinations = 0
        triggers = set()
        kinds = set()

        def dereference(value):
            nonlocal reference_count
            encountered = set()
            while isinstance(value, IndirectObject):
                key = (value.idnum, value.generation)
                if key in encountered:
                    raise PDFAutomaticActionError(_ERROR)
                encountered.add(key)
                reference_count += 1
                if reference_count > MAX_REFERENCES:
                    raise PDFAutomaticActionError(_ERROR)
                value = value.get_object()
            if value is None or isinstance(value, NullObject):
                raise PDFAutomaticActionError(_ERROR)
            return value

        def require_dict(value):
            resolved = dereference(value)
            if not isinstance(resolved, DictionaryObject) or isinstance(
                resolved, StreamObject
            ):
                raise PDFAutomaticActionError(_ERROR)
            return resolved

        def require_array(value):
            resolved = dereference(value)
            if not isinstance(resolved, ArrayObject):
                raise PDFAutomaticActionError(_ERROR)
            return resolved

        def inspect_action(value, trigger, ancestors=frozenset()):
            nonlocal action_count
            if len(ancestors) >= MAX_ACTION_DEPTH:
                raise PDFAutomaticActionError(_ERROR)
            refkey = (
                ("ref", value.idnum, value.generation)
                if isinstance(value, IndirectObject)
                else ("direct", id(value))
            )
            if refkey in ancestors:
                raise PDFAutomaticActionError(_ERROR)
            chain = ancestors | {refkey}
            entry = require_dict(value)
            kind = entry.get("/S")
            if not isinstance(kind, NameObject) or not str(kind).startswith("/"):
                raise PDFAutomaticActionError(_ERROR)
            # Do not expose arbitrary action identifiers or any PDF payload.
            kinds.add(str(kind)[1:] if str(kind) in _KNOWN_ACTIONS else "other")
            triggers.add(trigger)
            action_count += 1
            if action_count > MAX_ACTIONS:
                raise PDFAutomaticActionError(_ERROR)
            if kind == "/JavaScript":
                script = entry.get("/JS")
                if script is None:
                    raise PDFAutomaticActionError(_ERROR)
                script = dereference(script)
                if not isinstance(script, (TextStringObject, ByteStringObject, StreamObject)):
                    raise PDFAutomaticActionError(_ERROR)
                # The private hook allows a bounded payload inspector to reuse
                # the full action/trigger graph without repeating that traversal.
                # This automatic-action inspector never interprets scripts.
                if _javascript_inspector is not None:
                    _javascript_inspector(script, trigger)
            next_action = entry.get("/Next")
            if next_action is not None:
                next_action = dereference(next_action)
                if isinstance(next_action, ArrayObject):
                    if len(next_action) > MAX_ACTIONS:
                        raise PDFAutomaticActionError(_ERROR)
                    for next_item in next_action:
                        inspect_action(next_item, trigger, chain)
                else:
                    inspect_action(next_action, trigger, chain)

        def inspect_additional(value, trigger):
            additional = require_dict(value)
            if len(additional) > MAX_ACTIONS:
                raise PDFAutomaticActionError(_ERROR)
            for event, value in additional.items():
                if not isinstance(event, NameObject):
                    raise PDFAutomaticActionError(_ERROR)
                inspect_action(value, trigger)

        open_action = root.get("/OpenAction")
        if open_action is not None:
            obj = dereference(open_action)
            if isinstance(obj, DictionaryObject):
                inspect_action(open_action, "document_open")
            elif isinstance(obj, (ArrayObject, NameObject, TextStringObject)):
                open_destinations += 1
                triggers.add("document_open_destination")
            else:
                raise PDFAutomaticActionError(_ERROR)

        if "/AA" in root:
            inspect_additional(root["/AA"], "document_additional")

        names = root.get("/Names")
        if names is not None:
            names = require_dict(names)
            javascript = names.get("/JavaScript")
            if javascript is not None:
                seen_trees = set()
                tree_nodes = 0

                def walk_names(value, depth=0):
                    nonlocal tree_nodes
                    if depth >= MAX_ACTION_DEPTH:
                        raise PDFAutomaticActionError(_ERROR)
                    node = require_dict(value)
                    identity = id(node)
                    if identity in seen_trees:
                        raise PDFAutomaticActionError(_ERROR)
                    seen_trees.add(identity)
                    tree_nodes += 1
                    if tree_nodes > MAX_TREE_NODES:
                        raise PDFAutomaticActionError(_ERROR)
                    pairs = node.get("/Names")
                    kids = node.get("/Kids")
                    if (pairs is None) == (kids is None):
                        raise PDFAutomaticActionError(_ERROR)
                    if pairs is not None:
                        entries = require_array(pairs)
                        if len(entries) % 2 or len(entries) > MAX_ACTIONS * 2:
                            raise PDFAutomaticActionError(_ERROR)
                        for index in range(0, len(entries), 2):
                            key = dereference(entries[index])
                            if not isinstance(key, (TextStringObject, NameObject)):
                                raise PDFAutomaticActionError(_ERROR)
                            inspect_action(entries[index + 1], "document_javascript")
                    else:
                        children = require_array(kids)
                        if not children or len(children) > MAX_TREE_NODES:
                            raise PDFAutomaticActionError(_ERROR)
                        for child in children:
                            walk_names(child, depth + 1)

                walk_names(javascript)

        field_total = 0
        form = root.get("/AcroForm")
        if form is not None:
            form = require_dict(form)
            roots = form.get("/Fields")
            if roots is not None:
                seen_fields = set()

                def inspect_field(value, depth=0):
                    nonlocal field_total
                    if depth >= MAX_ACTION_DEPTH:
                        raise PDFAutomaticActionError(_ERROR)
                    field = require_dict(value)
                    identity = id(field)
                    if identity in seen_fields:
                        raise PDFAutomaticActionError(_ERROR)
                    seen_fields.add(identity)
                    field_total += 1
                    if field_total > MAX_FIELDS:
                        raise PDFAutomaticActionError(_ERROR)
                    if "/AA" in field:
                        inspect_additional(field["/AA"], "field_additional")
                    if "/Kids" in field:
                        for child in require_array(field["/Kids"]):
                            inspect_field(child, depth + 1)

                for item in require_array(roots):
                    inspect_field(item)

        annotation_total = 0
        for page in reader.pages:
            if "/AA" in page:
                inspect_additional(page["/AA"], "page_additional")
            if "/Annots" in page:
                for annotation in require_array(page["/Annots"]):
                    annotation_total += 1
                    if annotation_total > MAX_ANNOTATIONS:
                        raise PDFAutomaticActionError(_ERROR)
                    entry = require_dict(annotation)
                    if "/AA" in entry:
                        inspect_additional(entry["/AA"], "annotation_additional")

        return PDFAutomaticActionInspection(
            action_count=action_count,
            open_destination_count=open_destinations,
            trigger_types=tuple(sorted(triggers)),
            action_types=tuple(sorted(kinds)),
        )
    except PDFAutomaticActionError:
        raise
    except Exception:
        # Never leak arbitrary document text or filesystem details from pypdf.
        raise PDFAutomaticActionError(_ERROR) from None
