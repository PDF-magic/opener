"""Passive, bounded inspection of PDF form actions for planned Enhanced protection.

No PDF-provided target, field value, JavaScript, or action is executed. Findings
never authorize the existing Built-in scanner to open a document.
"""
from dataclasses import dataclass
from io import BytesIO

MAX_PDF_BYTES = 16 * 1024 * 1024
MAX_INDIRECT_OBJECTS = 4096
MAX_GRAPH_NODES = 65536
MAX_FORM_ACTIONS = 512
MAX_FIELD_SELECTORS = 4096
MAX_PAGES = 1024
BLOCK_MESSAGE = "PDF form actions could not be fully inspected; opening was stopped."
FORM_ACTIONS = {"/SubmitForm": "submit", "/ResetForm": "reset", "/ImportData": "import"}


class PDFFormActionInspectionError(RuntimeError):
    """Fixed path-free indication of an uninspectable form action."""


@dataclass(frozen=True)
class PDFFormActionInspection:
    action_count: int
    action_kinds: tuple[str, ...]
    field_selector_count: int
    has_submission_target: bool
    permits_open: bool = False

    def __post_init__(self):
        if (type(self.action_count) is not int or
                not 0 <= self.action_count <= MAX_FORM_ACTIONS or
                type(self.action_kinds) is not tuple or
                self.action_kinds != tuple(sorted(set(self.action_kinds))) or
                any(kind not in FORM_ACTIONS.values() for kind in self.action_kinds) or
                bool(self.action_count) != bool(self.action_kinds) or
                type(self.field_selector_count) is not int or
                not 0 <= self.field_selector_count <= MAX_FIELD_SELECTORS or
                type(self.has_submission_target) is not bool or
                self.has_submission_target != ("submit" in self.action_kinds) or
                self.permits_open is not False):
            raise ValueError("Form action findings cannot authorize opening")

    @property
    def has_form_actions(self) -> bool:
        return self.action_count > 0


def inspect_pdf_form_actions(contents: bytes) -> PDFFormActionInspection:
    """Inspect all indexed PDF form actions, including orphaned and chained ones.

    Accept only immutable in-memory bytes. Do not return raw action targets or
    field names, which may contain sensitive information. Fail closed when the
    strict parser or the bounded graph inspection cannot finish.
    """
    if type(contents) is not bytes or not contents or len(contents) > MAX_PDF_BYTES:
        raise PDFFormActionInspectionError(BLOCK_MESSAGE)
    try:
        from pypdf import PdfReader
        from pypdf.generic import (
            ArrayObject, ByteStringObject, DictionaryObject, IndirectObject,
            NameObject, NumberObject, TextStringObject,
        )
    except (ImportError, OSError) as exc:
        raise PDFFormActionInspectionError(BLOCK_MESSAGE) from exc

    try:
        reader = PdfReader(BytesIO(contents), strict=True)
        if reader.is_encrypted or reader.xref_objStm or len(reader.pages) > MAX_PAGES:
            raise PDFFormActionInspectionError(BLOCK_MESSAGE)

        roots = [reader.trailer]
        indexed = 0
        for generation, offsets in reader.xref.items():
            if type(generation) is not int or not 0 <= generation <= 65535:
                raise PDFFormActionInspectionError(BLOCK_MESSAGE)
            for number, offset in offsets.items():
                if number == 0:
                    continue
                if (type(number) is not int or type(offset) is not int or
                        number < 1 or offset <= 0):
                    raise PDFFormActionInspectionError(BLOCK_MESSAGE)
                indexed += 1
                if indexed > MAX_INDIRECT_OBJECTS:
                    raise PDFFormActionInspectionError(BLOCK_MESSAGE)
                roots.append(IndirectObject(number, generation, reader))

        references = {}
        examined = set()
        kinds = set()
        count = 0
        field_count = 0
        visited = 0

        def resolve(obj):
            chain = set()
            while isinstance(obj, IndirectObject):
                key = (obj.idnum, obj.generation)
                if key in chain:
                    raise PDFFormActionInspectionError(BLOCK_MESSAGE)
                chain.add(key)
                if key not in references:
                    if len(references) >= MAX_INDIRECT_OBJECTS:
                        raise PDFFormActionInspectionError(BLOCK_MESSAGE)
                    references[key] = obj.get_object()
                obj = references[key]
                if obj is None:
                    raise PDFFormActionInspectionError(BLOCK_MESSAGE)
            return obj

        def valid_file_spec(value):
            value = resolve(value)
            if isinstance(value, (TextStringObject, ByteStringObject)) and value:
                return True
            if isinstance(value, DictionaryObject):
                return any(
                    name in value and isinstance(
                        resolve(value.raw_get(name)),
                        (TextStringObject, ByteStringObject)
                    ) and bool(resolve(value.raw_get(name)))
                    for name in ("/F", "/UF")
                )
            return False

        def inspect_action(node, kind):
            nonlocal count, field_count
            count += 1
            if count > MAX_FORM_ACTIONS:
                raise PDFFormActionInspectionError(BLOCK_MESSAGE)
            kinds.add(kind)
            if kind in ("submit", "import"):
                if "/F" not in node or not valid_file_spec(node.raw_get("/F")):
                    raise PDFFormActionInspectionError(BLOCK_MESSAGE)
            if "/Fields" in node:
                if kind == "import":
                    raise PDFFormActionInspectionError(BLOCK_MESSAGE)
                fields = resolve(node.raw_get("/Fields"))
                if not isinstance(fields, ArrayObject):
                    raise PDFFormActionInspectionError(BLOCK_MESSAGE)
                field_count += len(fields)
                if field_count > MAX_FIELD_SELECTORS:
                    raise PDFFormActionInspectionError(BLOCK_MESSAGE)
                for entry in fields:
                    item = resolve(entry)
                    if not (isinstance(item, DictionaryObject) or
                            isinstance(item, (TextStringObject, ByteStringObject)) and item):
                        raise PDFFormActionInspectionError(BLOCK_MESSAGE)
            if "/Flags" in node:
                flags = resolve(node.raw_get("/Flags"))
                if (type(flags) is not NumberObject or
                        not 0 <= int(flags) <= 0xFFFFFFFF or
                        kind == "import" or
                        (kind == "reset" and flags & ~1)):
                    raise PDFFormActionInspectionError(BLOCK_MESSAGE)
            if "/Next" in node:
                nxt = resolve(node.raw_get("/Next"))
                chain = nxt if isinstance(nxt, ArrayObject) else [nxt]
                if any(not isinstance(resolve(x), DictionaryObject) for x in chain):
                    raise PDFFormActionInspectionError(BLOCK_MESSAGE)

        stack = roots
        while stack:
            node = resolve(stack.pop())
            visited += 1
            if visited > MAX_GRAPH_NODES:
                raise PDFFormActionInspectionError(BLOCK_MESSAGE)
            if isinstance(node, (DictionaryObject, ArrayObject)):
                if id(node) in examined:
                    continue
                examined.add(id(node))
                if isinstance(node, DictionaryObject):
                    subtype = resolve(node.raw_get("/S")) if "/S" in node else None
                    if subtype in FORM_ACTIONS:
                        inspect_action(node, FORM_ACTIONS[subtype])
                    stack.extend(node.raw_get(key) for key in node.keys())
                else:
                    stack.extend(node)

        return PDFFormActionInspection(
            count, tuple(sorted(kinds)), field_count, "submit" in kinds
        )
    except PDFFormActionInspectionError:
        raise
    except Exception as exc:
        raise PDFFormActionInspectionError(BLOCK_MESSAGE) from exc
