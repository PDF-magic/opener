"""Identify external-request actions reachable through PDF automatic triggers.

This is optional Enhanced evidence, never an installed scan-gate decision. It
does not execute actions or JavaScript, decode streams, follow hyperlinks,
resolve DNS, access a network, or authorize opening a PDF. Plain clickable
annotation /A links are deliberately not classified as automatic requests.
"""

from dataclasses import dataclass, field
from io import BytesIO

from pdf_structure_parser import PDFStructureParseError, parse_pdf_structure

MAX_ACTIONS = 512
MAX_REFERENCES = 4096
MAX_DEPTH = 64
MAX_FIELDS = 512
MAX_ANNOTATIONS = 2048
MAX_TREE_NODES = 256
_ERROR = "Automatic PDF external requests could not be fully inspected; opening was stopped."

_REQUEST_KINDS = frozenset((
    "uri_action", "form_submission", "form_import",
    "remote_document", "launch_url",
))
_CONTEXTS = frozenset((
    "document_open", "document_event", "page_event",
    "field_event", "annotation_event",
))
_REMOTE_SCHEMES = ("http:", "https:", "ftp:", "ws:", "wss:", "file://")


class PDFAutomaticExternalRequestError(RuntimeError):
    """Fixed content-free error on incomplete or ambiguous inspection."""


@dataclass(frozen=True)
class PDFAutomaticExternalRequests:
    """Fixed, bounded and private evidence, not an opening authorization."""

    startup_request_count: int
    event_request_count: int
    unassessed_script_count: int
    request_kinds: tuple[str, ...]
    trigger_contexts: tuple[str, ...]
    authorizes_open: bool = field(default=False, init=False)

    def __post_init__(self):
        counts = (
            self.startup_request_count, self.event_request_count,
            self.unassessed_script_count,
        )
        if (
            any(type(number) is not int or not 0 <= number <= MAX_ACTIONS
                for number in counts)
            or sum(counts) > MAX_ACTIONS
            or type(self.request_kinds) is not tuple
            or type(self.trigger_contexts) is not tuple
            or self.request_kinds != tuple(sorted(set(self.request_kinds)))
            or self.trigger_contexts != tuple(sorted(set(self.trigger_contexts)))
            or any(type(name) is not str or name not in _REQUEST_KINDS
                   for name in self.request_kinds)
            or any(type(name) is not str or name not in _CONTEXTS
                   for name in self.trigger_contexts)
            or bool(self.startup_request_count + self.event_request_count)
            != bool(self.request_kinds)
            or self.authorizes_open is not False
        ):
            raise ValueError("Invalid automatic external request evidence")

    @property
    def has_potential_external_requests(self) -> bool:
        return self.startup_request_count + self.event_request_count > 0

    def to_dict(self) -> dict:
        """Expose no document URLs, script text, paths or private form values."""
        return {
            "schemaVersion": 1,
            "documentOpenRequestCount": self.startup_request_count,
            "eventTriggeredRequestCount": self.event_request_count,
            "unassessedScriptCount": self.unassessed_script_count,
            "requestKinds": list(self.request_kinds),
            "triggerContexts": list(self.trigger_contexts),
            "authorizesOpen": False,
        }


def inspect_pdf_automatic_external_requests(contents: bytes) -> PDFAutomaticExternalRequests:
    """Correlate explicit remote targets with /OpenAction or /AA action chains.

    /AA actions depend on document/page/widget events, so their results are
    labeled event-triggered, not unconditional document-open requests.
    Javascript is opaque and *not* presumed safe; script counts describe
    unassessed network potential, not confirmed HTTP traffic.
    """
    try:
        parse_pdf_structure(contents)
    except PDFStructureParseError:
        raise PDFAutomaticExternalRequestError(_ERROR) from None

    try:
        from pypdf import PdfReader
        from pypdf.generic import (
            ArrayObject, ByteStringObject, DictionaryObject, IndirectObject,
            NameObject, StreamObject, TextStringObject,
        )
        from pdf_suspicious_urls import _classify_url, _read_url
    except (ImportError, OSError):
        raise PDFAutomaticExternalRequestError(_ERROR) from None

    try:
        reader = PdfReader(BytesIO(contents), strict=True)
        if reader.is_encrypted:
            raise PDFAutomaticExternalRequestError(_ERROR)
        reference_count = 0
        action_count = 0
        startup = events = scripts = 0
        kinds = set()
        contexts = set()

        def resolve(value):
            nonlocal reference_count
            encountered = set()
            while isinstance(value, IndirectObject):
                reference = (value.idnum, value.generation)
                if reference in encountered:
                    raise PDFAutomaticExternalRequestError(_ERROR)
                encountered.add(reference)
                reference_count += 1
                if reference_count > MAX_REFERENCES:
                    raise PDFAutomaticExternalRequestError(_ERROR)
                value = value.get_object()
            if value is None:
                raise PDFAutomaticExternalRequestError(_ERROR)
            return value

        def dictionary(value):
            resolved = resolve(value)
            if (not isinstance(resolved, DictionaryObject)
                    or isinstance(resolved, StreamObject)):
                raise PDFAutomaticExternalRequestError(_ERROR)
            return resolved

        def array(value):
            resolved = resolve(value)
            if not isinstance(resolved, ArrayObject):
                raise PDFAutomaticExternalRequestError(_ERROR)
            return resolved

        def remote_target(value):
            """Return a validated URL presence flag, never the URL itself."""
            target = resolve(value)
            url_filespec = False
            if isinstance(target, DictionaryObject):
                mode = target.get("/FS")
                if mode is not None and not isinstance(mode, NameObject):
                    raise PDFAutomaticExternalRequestError(_ERROR)
                url_filespec = mode == "/URL"
                if "/UF" in target:
                    target = resolve(target.raw_get("/UF"))
                elif "/F" in target:
                    target = resolve(target.raw_get("/F"))
                else:
                    raise PDFAutomaticExternalRequestError(_ERROR)
            if not isinstance(target, (TextStringObject, ByteStringObject)):
                raise PDFAutomaticExternalRequestError(_ERROR)
            # Decode and validate with the existing non-networking URL parser.
            value = _read_url(target)
            remote = url_filespec or value.lower().startswith(_REMOTE_SCHEMES) or value.startswith("//")
            if remote:
                _classify_url(target)
            return bool(remote)

        def inspect_action(value, context, ancestors=frozenset(), depth=0):
            nonlocal action_count, startup, events, scripts
            if depth >= MAX_DEPTH:
                raise PDFAutomaticExternalRequestError(_ERROR)
            action = dictionary(value)
            identity = id(action)
            if identity in ancestors:
                raise PDFAutomaticExternalRequestError(_ERROR)
            lineage = ancestors | {identity}
            action_count += 1
            if action_count > MAX_ACTIONS:
                raise PDFAutomaticExternalRequestError(_ERROR)
            kind = action.get("/S")
            if not isinstance(kind, NameObject) or not str(kind).startswith("/"):
                raise PDFAutomaticExternalRequestError(_ERROR)

            matched = None
            if kind == "/URI":
                if "/URI" not in action:
                    raise PDFAutomaticExternalRequestError(_ERROR)
                target = resolve(action.raw_get("/URI"))
                _classify_url(target)
                matched = "uri_action"
            elif kind in ("/SubmitForm", "/ImportData", "/GoToR", "/GoToE", "/Launch"):
                if "/F" in action and remote_target(action.raw_get("/F")):
                    matched = {
                        "/SubmitForm": "form_submission",
                        "/ImportData": "form_import",
                        "/GoToR": "remote_document",
                        "/GoToE": "remote_document",
                        "/Launch": "launch_url",
                    }[str(kind)]
                elif kind in ("/SubmitForm", "/GoToR") and "/F" not in action:
                    raise PDFAutomaticExternalRequestError(_ERROR)
            elif kind == "/JavaScript":
                # Script contents can dynamically request the network.
                # Neither executing nor token-matching scripts is safe proof.
                if "/JS" not in action:
                    raise PDFAutomaticExternalRequestError(_ERROR)
                js = resolve(action.raw_get("/JS"))
                if not isinstance(js, (TextStringObject, ByteStringObject, StreamObject)):
                    raise PDFAutomaticExternalRequestError(_ERROR)
                scripts += 1

            if matched:
                kinds.add(matched)
                contexts.add(context)
                if context == "document_open":
                    startup += 1
                else:
                    events += 1

            if "/Next" in action:
                following = resolve(action.raw_get("/Next"))
                if isinstance(following, ArrayObject):
                    if not following or len(following) > MAX_ACTIONS:
                        raise PDFAutomaticExternalRequestError(_ERROR)
                    for item in following:
                        inspect_action(item, context, lineage, depth + 1)
                else:
                    inspect_action(following, context, lineage, depth + 1)

        def additional(value, context):
            entries = dictionary(value)
            if len(entries) > MAX_ACTIONS:
                raise PDFAutomaticExternalRequestError(_ERROR)
            for event in entries.keys():
                if not isinstance(event, NameObject):
                    raise PDFAutomaticExternalRequestError(_ERROR)
                inspect_action(entries.raw_get(event), context)

        root = dictionary(reader.trailer.raw_get("/Root"))
        if "/OpenAction" in root:
            opener = resolve(root.raw_get("/OpenAction"))
            if isinstance(opener, DictionaryObject):
                inspect_action(opener, "document_open")
            elif not isinstance(opener, (ArrayObject, NameObject, TextStringObject)):
                raise PDFAutomaticExternalRequestError(_ERROR)
        if "/AA" in root:
            additional(root.raw_get("/AA"), "document_event")

        for page in reader.pages:
            if "/AA" in page:
                additional(page.raw_get("/AA"), "page_event")
            if "/Annots" in page:
                annotations = array(page.raw_get("/Annots"))
                if len(annotations) > MAX_ANNOTATIONS:
                    raise PDFAutomaticExternalRequestError(_ERROR)
                for item in annotations:
                    annotation = dictionary(item)
                    # /A is click-only and is intentionally not automatic.
                    if "/AA" in annotation:
                        additional(annotation.raw_get("/AA"), "annotation_event")

        if "/AcroForm" in root:
            form = dictionary(root.raw_get("/AcroForm"))
            if "/Fields" in form:
                seen = set()
                def field_walk(value, depth=0):
                    if depth >= MAX_DEPTH:
                        raise PDFAutomaticExternalRequestError(_ERROR)
                    entry = dictionary(value)
                    identity = id(entry)
                    if identity in seen:
                        raise PDFAutomaticExternalRequestError(_ERROR)
                    seen.add(identity)
                    if len(seen) > MAX_FIELDS:
                        raise PDFAutomaticExternalRequestError(_ERROR)
                    if "/AA" in entry:
                        additional(entry.raw_get("/AA"), "field_event")
                    if "/Kids" in entry:
                        for kid in array(entry.raw_get("/Kids")):
                            field_walk(kid, depth + 1)
                for entry in array(form.raw_get("/Fields")):
                    field_walk(entry)

        return PDFAutomaticExternalRequests(
            startup, events, scripts, tuple(sorted(kinds)),
            tuple(sorted(contexts)),
        )
    except PDFAutomaticExternalRequestError:
        raise
    except Exception:
        # pypdf/URL parser exceptions may contain PDF strings or local paths.
        raise PDFAutomaticExternalRequestError(_ERROR) from None
