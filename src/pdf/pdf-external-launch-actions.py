"""Bounded passive inspection of external PDF launch actions (opener-0288).

This planned Enhanced stage does not execute targets, change the Built-in
scanner policy, or grant permission to open any document.
"""
from dataclasses import dataclass
from io import BytesIO
from types import MappingProxyType

MAX_PDF_BYTES = 16 * 1024 * 1024
MAX_INDIRECT_OBJECTS = 4096
MAX_GRAPH_NODES = 65536
MAX_EXTERNAL_ACTIONS = 512
MAX_PAGES = 1024
BLOCK_MESSAGE = "PDF external launch actions could not be fully inspected; opening was stopped."

EXTERNAL_ACTIONS = MappingProxyType({
    "/Launch": "launch",
    "/GoToR": "remote_goto",
    "/GoToE": "embedded_goto",
    "/URI": "uri",
    "/SubmitForm": "submit_form",
    "/ImportData": "import_data",
})


class PDFExternalLaunchInspectionError(RuntimeError):
    """Fixed path-free indication of an uninspectable external action."""


@dataclass(frozen=True)
class PDFExternalLaunchInspection:
    action_count: int
    action_kinds: tuple[str, ...]
    target_kinds: tuple[str, ...]
    permits_open: bool = False

    def __post_init__(self):
        if (type(self.action_count) is not int or self.action_count < 0 or
                self.action_count > MAX_EXTERNAL_ACTIONS or
                type(self.action_kinds) is not tuple or
                any(x not in EXTERNAL_ACTIONS.values() for x in self.action_kinds) or
                type(self.target_kinds) is not tuple or
                any(x not in ("file", "windows_command", "uri", "form")
                    for x in self.target_kinds) or
                self.action_kinds != tuple(sorted(set(self.action_kinds))) or
                self.target_kinds != tuple(sorted(set(self.target_kinds))) or
                bool(self.action_count) != bool(self.action_kinds) or
                self.permits_open is not False):
            raise ValueError("External action findings cannot authorize opening")

    @property
    def has_external_actions(self) -> bool:
        return self.action_count > 0


def inspect_pdf_external_launch_actions(contents: bytes) -> PDFExternalLaunchInspection:
    """Inspect PDF action dictionaries throughout indexed objects and /Next chains.

    Enumerating all strict-parser xref objects covers catalog, page, annotation,
    form, outline and otherwise orphaned actions. Document-supplied target
    values are never returned, followed, launched or evaluated.
    """
    if type(contents) is not bytes or not contents or len(contents) > MAX_PDF_BYTES:
        raise PDFExternalLaunchInspectionError(BLOCK_MESSAGE)
    try:
        from pypdf import PdfReader
        from pypdf.generic import (
            ArrayObject, BooleanObject, ByteStringObject, DictionaryObject,
            IndirectObject, NameObject, TextStringObject,
        )
    except (ImportError, OSError) as exc:
        raise PDFExternalLaunchInspectionError(BLOCK_MESSAGE) from exc

    try:
        reader = PdfReader(BytesIO(contents), strict=True)
        if reader.is_encrypted or reader.xref_objStm or len(reader.pages) > MAX_PAGES:
            raise PDFExternalLaunchInspectionError(BLOCK_MESSAGE)

        roots = [reader.trailer]
        indexed = 0
        for generation, offsets in reader.xref.items():
            if type(generation) is not int or not 0 <= generation <= 65535:
                raise PDFExternalLaunchInspectionError(BLOCK_MESSAGE)
            for number, offset in offsets.items():
                if number == 0:
                    continue
                if (type(number) is not int or type(offset) is not int or
                        number < 1 or offset <= 0):
                    raise PDFExternalLaunchInspectionError(BLOCK_MESSAGE)
                indexed += 1
                if indexed > MAX_INDIRECT_OBJECTS:
                    raise PDFExternalLaunchInspectionError(BLOCK_MESSAGE)
                roots.append(IndirectObject(number, generation, reader))

        cached_refs = {}
        examined_containers = set()
        kinds, targets = set(), set()
        count, visited = 0, 0

        def resolve(value):
            chain = set()
            while isinstance(value, IndirectObject):
                key = (value.idnum, value.generation)
                if key in chain:
                    raise PDFExternalLaunchInspectionError(BLOCK_MESSAGE)
                chain.add(key)
                if key not in cached_refs:
                    if len(cached_refs) >= MAX_INDIRECT_OBJECTS:
                        raise PDFExternalLaunchInspectionError(BLOCK_MESSAGE)
                    cached_refs[key] = value.get_object()
                value = cached_refs[key]
                if value is None:
                    raise PDFExternalLaunchInspectionError(BLOCK_MESSAGE)
            return value

        def is_string(value):
            value = resolve(value)
            return isinstance(value, (TextStringObject, ByteStringObject)) and bool(value)

        def check_file(value):
            value = resolve(value)
            if isinstance(value, (TextStringObject, ByteStringObject)) and value:
                return
            if isinstance(value, DictionaryObject) and any(
                k in value and is_string(value.raw_get(k)) for k in ("/F", "/UF")
            ):
                return
            raise PDFExternalLaunchInspectionError(BLOCK_MESSAGE)

        def inspect_action(node, kind):
            nonlocal count
            count += 1
            if count > MAX_EXTERNAL_ACTIONS:
                raise PDFExternalLaunchInspectionError(BLOCK_MESSAGE)
            kinds.add(kind)
            if kind == "launch":
                if "/F" in node:
                    check_file(node.raw_get("/F"))
                    targets.add("file")
                if "/Win" in node:
                    win = resolve(node.raw_get("/Win"))
                    if not isinstance(win, DictionaryObject) or "/F" not in win:
                        raise PDFExternalLaunchInspectionError(BLOCK_MESSAGE)
                    if not is_string(win.raw_get("/F")):
                        raise PDFExternalLaunchInspectionError(BLOCK_MESSAGE)
                    for key in ("/D", "/O", "/P"):
                        if key in win and not is_string(win.raw_get(key)):
                            raise PDFExternalLaunchInspectionError(BLOCK_MESSAGE)
                    targets.add("windows_command")
                if "/F" not in node and "/Win" not in node:
                    raise PDFExternalLaunchInspectionError(BLOCK_MESSAGE)
            elif kind in ("remote_goto", "embedded_goto"):
                if kind == "remote_goto" and "/F" not in node:
                    raise PDFExternalLaunchInspectionError(BLOCK_MESSAGE)
                if "/F" in node:
                    check_file(node.raw_get("/F"))
                    targets.add("file")
                if "/D" not in node or not isinstance(
                    resolve(node.raw_get("/D")),
                    (ArrayObject, NameObject, TextStringObject, ByteStringObject)
                ):
                    raise PDFExternalLaunchInspectionError(BLOCK_MESSAGE)
            elif kind == "uri":
                if "/URI" not in node or not is_string(node.raw_get("/URI")):
                    raise PDFExternalLaunchInspectionError(BLOCK_MESSAGE)
                targets.add("uri")
            elif kind in ("submit_form", "import_data"):
                if "/F" not in node:
                    raise PDFExternalLaunchInspectionError(BLOCK_MESSAGE)
                check_file(node.raw_get("/F"))
                targets.add("form")
            if "/NewWindow" in node and not isinstance(
                resolve(node.raw_get("/NewWindow")), BooleanObject
            ):
                raise PDFExternalLaunchInspectionError(BLOCK_MESSAGE)
            if "/Next" in node:
                next_obj = resolve(node.raw_get("/Next"))
                chain = next_obj if isinstance(next_obj, ArrayObject) else [next_obj]
                if any(not isinstance(resolve(x), DictionaryObject) for x in chain):
                    raise PDFExternalLaunchInspectionError(BLOCK_MESSAGE)

        stack = roots
        while stack:
            node = resolve(stack.pop())
            visited += 1
            if visited > MAX_GRAPH_NODES:
                raise PDFExternalLaunchInspectionError(BLOCK_MESSAGE)
            if isinstance(node, (DictionaryObject, ArrayObject)):
                if id(node) in examined_containers:
                    continue
                examined_containers.add(id(node))
                if isinstance(node, DictionaryObject):
                    subtype = node.raw_get("/S") if "/S" in node else None
                    if subtype in EXTERNAL_ACTIONS:
                        inspect_action(node, EXTERNAL_ACTIONS[subtype])
                    stack.extend(node.raw_get(k) for k in node.keys())
                else:
                    stack.extend(node)

        return PDFExternalLaunchInspection(
            count, tuple(sorted(kinds)), tuple(sorted(targets))
        )
    except PDFExternalLaunchInspectionError:
        raise
    except Exception as exc:
        raise PDFExternalLaunchInspectionError(BLOCK_MESSAGE) from exc
