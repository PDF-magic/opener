"""Report unusual PDF action chains as inert evidence for planned Enhanced checks.

Inspect actual /Next links across all indexed PDF objects, including orphaned
actions and annotations. Never execute actions, decode streams, or authorize
opening. This is separate from the installed ClamAV scanner.
"""

from dataclasses import dataclass, field
from io import BytesIO

from pdf_structure_parser import PDFStructureParseError, parse_pdf_structure


MAX_INDIRECT_OBJECTS = 4096
MAX_GRAPH_NODES = 65536
MAX_CHAIN_ROOTS = 512
MAX_CHAIN_VISITS = 32768
MAX_CHAIN_DEPTH = 64
MAX_CHAIN_WIDTH = 128
UNUSUAL_CHAIN_DEPTH = 8
UNUSUAL_CHAIN_WIDTH = 8

_FINDING_CODES = frozenset((
    "cycle", "repeated_action", "competing_navigation",
    "conflicting_form_operations", "mixed_launch_navigation",
    "deep_chain", "wide_chain",
))
_NAVIGATION = frozenset(("/GoTo", "/GoToR", "/GoToE"))
_FORM_RESET_CONFLICTS = frozenset(("/SubmitForm", "/ImportData"))
_ERROR = "PDF action chains could not be fully inspected; opening was stopped."


class PDFActionChainInspectionError(RuntimeError):
    """Fixed, PDF-content-free failure on incomplete chain inspection."""


@dataclass(frozen=True)
class PDFActionChainInspection:
    """Bounded metadata only; absence of findings is never a clean verdict."""

    chain_count: int
    finding_codes: tuple[str, ...]
    permits_open: bool = field(default=False, init=False)

    def __post_init__(self):
        if (type(self.chain_count) is not int or
                not 0 <= self.chain_count <= MAX_CHAIN_ROOTS or
                type(self.finding_codes) is not tuple or
                self.finding_codes != tuple(sorted(set(self.finding_codes))) or
                any(type(code) is not str or code not in _FINDING_CODES
                    for code in self.finding_codes) or
                self.permits_open is not False):
            raise ValueError("Action chain findings cannot authorize opening")

    @property
    def has_unusual_chains(self) -> bool:
        return bool(self.finding_codes)

    def to_dict(self) -> dict:
        """Return detached JSON-safe metadata, never PDF-provided strings."""
        return {
            "schemaVersion": 1,
            "chainCount": self.chain_count,
            "findingCodes": list(self.finding_codes),
            "authorizesOpen": False,
        }


def inspect_pdf_action_chains(contents: bytes) -> PDFActionChainInspection:
    """Find suspicious /Next action sequences, not arbitrary outline /Next links.

    Treat all actions in a /Next array as part of the same sequence. Identify
    competing navigation, mutually inconsistent form operations, launch plus
    navigation, repeated actions, cycles, and excessive chain depth or width.
    Graph and chain work are bounded. Invalid links fail closed.
    """
    try:
        parse_pdf_structure(contents)
    except PDFStructureParseError:
        raise PDFActionChainInspectionError(_ERROR) from None

    try:
        from pypdf import PdfReader
        from pypdf.generic import (
            ArrayObject, DictionaryObject, IndirectObject, NameObject,
            StreamObject,
        )
    except (ImportError, OSError):
        raise PDFActionChainInspectionError(_ERROR) from None

    try:
        reader = PdfReader(BytesIO(contents), strict=True)
        if reader.is_encrypted or reader.xref_objStm:
            raise PDFActionChainInspectionError(_ERROR)

        roots = [reader.trailer]
        indexed = 0
        for generation, objects in reader.xref.items():
            if type(generation) is not int or not 0 <= generation <= 65535:
                raise PDFActionChainInspectionError(_ERROR)
            for number, offset in objects.items():
                if number == 0:
                    continue
                if (type(number) is not int or type(offset) is not int or
                        number < 1 or offset <= 0):
                    raise PDFActionChainInspectionError(_ERROR)
                indexed += 1
                if indexed > MAX_INDIRECT_OBJECTS:
                    raise PDFActionChainInspectionError(_ERROR)
                roots.append(IndirectObject(number, generation, reader))

        reference_count = 0

        def resolve(value):
            nonlocal reference_count
            seen = set()
            while isinstance(value, IndirectObject):
                ref = (value.idnum, value.generation)
                if ref in seen:
                    raise PDFActionChainInspectionError(_ERROR)
                seen.add(ref)
                reference_count += 1
                if reference_count > MAX_GRAPH_NODES:
                    raise PDFActionChainInspectionError(_ERROR)
                value = value.get_object()
            return value

        # The global object index finds orphaned and click-triggered /A actions
        # that the narrower automatic-action inspector does not enumerate.
        stack = roots
        examined = set()
        chain_roots = []
        visited = 0
        while stack:
            node = resolve(stack.pop())
            if not isinstance(node, (DictionaryObject, ArrayObject)) or isinstance(
                node, StreamObject
            ):
                continue
            if id(node) in examined:
                continue
            examined.add(id(node))
            visited += 1
            if visited > MAX_GRAPH_NODES:
                raise PDFActionChainInspectionError(_ERROR)
            if isinstance(node, ArrayObject):
                stack.extend(node)
                continue
            if "/Next" in node and "/S" in node:
                chain_roots.append(node)
                if len(chain_roots) > MAX_CHAIN_ROOTS:
                    raise PDFActionChainInspectionError(_ERROR)
            stack.extend(node.raw_get(key) for key in node.keys())

        findings = set()
        chain_visits = 0
        for root in chain_roots:
            kinds = set()
            navigation_count = 0
            seen_nodes = set()
            # Walk with ancestry to distinguish a cycle from a shared action.
            pending = [(root, 1, frozenset())]
            while pending:
                value, depth, ancestors = pending.pop()
                node = resolve(value)
                if not isinstance(node, DictionaryObject) or isinstance(
                    node, StreamObject
                ):
                    raise PDFActionChainInspectionError(_ERROR)
                kind = node.raw_get("/S") if "/S" in node else None
                if not isinstance(kind, NameObject) or not str(kind).startswith("/"):
                    raise PDFActionChainInspectionError(_ERROR)
                identity = id(node)
                if identity in ancestors:
                    findings.add("cycle")
                    continue
                if identity in seen_nodes:
                    findings.add("repeated_action")
                    continue
                seen_nodes.add(identity)
                chain_visits += 1
                if chain_visits > MAX_CHAIN_VISITS or depth > MAX_CHAIN_DEPTH:
                    raise PDFActionChainInspectionError(_ERROR)
                if depth > UNUSUAL_CHAIN_DEPTH:
                    findings.add("deep_chain")
                kinds.add(str(kind))
                if kind in _NAVIGATION:
                    navigation_count += 1
                if "/Next" not in node:
                    continue
                following = resolve(node.raw_get("/Next"))
                if isinstance(following, ArrayObject):
                    if not following or len(following) > MAX_CHAIN_WIDTH:
                        raise PDFActionChainInspectionError(_ERROR)
                    if len(following) > UNUSUAL_CHAIN_WIDTH:
                        findings.add("wide_chain")
                    children = following
                else:
                    children = (following,)
                path = ancestors | {identity}
                for child in reversed(children):
                    pending.append((child, depth + 1, path))

            if navigation_count > 1:
                findings.add("competing_navigation")
            if "/ResetForm" in kinds and kinds.intersection(_FORM_RESET_CONFLICTS):
                findings.add("conflicting_form_operations")
            if "/Launch" in kinds and kinds.intersection(_NAVIGATION):
                findings.add("mixed_launch_navigation")

        return PDFActionChainInspection(
            chain_count=len(chain_roots),
            finding_codes=tuple(sorted(findings)),
        )
    except PDFActionChainInspectionError:
        raise
    except Exception:
        # pypdf exceptions may contain private PDF text, paths or targets.
        raise PDFActionChainInspectionError(_ERROR) from None
