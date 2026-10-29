"""Inspect embedded PDF filenames as bounded, non-executable metadata.

This optional Enhanced-only stage never opens attachments or authorizes opening
the outer PDF. Filename strings are private: return only trusted fixed flags.
"""
from dataclasses import dataclass
from io import BytesIO
import unicodedata

from enhanced_embedded_files import (
    MAX_NAME_TREE_NODES, _specifications,
)
from pdf_structure_parser import parse_pdf_structure

MAX_ATTACHMENTS = 32
MAX_FILENAME_CHARACTERS = 255
MAX_TOTAL_FILENAME_CHARACTERS = 8192
MAX_REFERENCES = 4096
BLOCK_MESSAGE = "Embedded PDF filenames could not be fully inspected; opening was stopped."

_KNOWN_FLAGS = frozenset((
    "path_component", "executable_extension", "disguised_extension",
    "unicode_direction", "invisible_character", "control_character",
    "trailing_separator", "name_disagreement",
))
_EXECUTABLE_EXTENSIONS = frozenset((
    "app", "bat", "cmd", "com", "dll", "exe", "hta", "jar", "js",
    "jse", "msi", "ps1", "py", "scr", "sh", "vbs", "wsf",
))
_DECOY_EXTENSIONS = frozenset((
    "doc", "docx", "gif", "jpeg", "jpg", "pdf", "png", "pptx",
    "rtf", "txt", "xlsx", "zip",
))
_DIRECTIONAL = frozenset((
    "\u061c", "\u200e", "\u200f", "\u202a", "\u202b", "\u202c",
    "\u202d", "\u202e", "\u2066", "\u2067", "\u2068", "\u2069",
))


class EmbeddedFilenameInspectionError(RuntimeError):
    """Incomplete metadata examination is not an absence-of-risk finding."""


@dataclass(frozen=True)
class EmbeddedFilenameInspection:
    specification_count: int
    name_tree_entry_count: int
    flagged_specification_count: int
    flags: tuple[str, ...]
    authorizes_open: bool = False

    def __post_init__(self):
        if (any(type(v) is not int or not 0 <= v <= MAX_ATTACHMENTS
                for v in (self.specification_count, self.name_tree_entry_count,
                          self.flagged_specification_count)) or
            self.flagged_specification_count > self.specification_count or
            type(self.flags) is not tuple or
            self.flags != tuple(sorted(set(self.flags))) or
            any(f not in _KNOWN_FLAGS for f in self.flags) or
            bool(self.flags) != bool(self.flagged_specification_count) or
            self.authorizes_open is not False):
            raise ValueError("Embedded filename metadata cannot authorize opening")

    @property
    def has_suspicious_filenames(self):
        return self.flagged_specification_count > 0


def _classify(name):
    """Use only string structure, never a filename as a filesystem path."""
    flags = set()
    if "/" in name or "\\" in name or ":" in name or name in (".", ".."):
        flags.add("path_component")
    if name.endswith((".", " ")):
        flags.add("trailing_separator")
    if any(ch in _DIRECTIONAL for ch in name):
        flags.add("unicode_direction")
    if any(unicodedata.category(ch) == "Cf" and ch not in _DIRECTIONAL
           for ch in name):
        flags.add("invisible_character")
    if any(unicodedata.category(ch) == "Cc" for ch in name):
        flags.add("control_character")
    suffixes = name.casefold().split(".")
    if len(suffixes) >= 2 and suffixes[-1] in _EXECUTABLE_EXTENSIONS:
        flags.add("executable_extension")
        if len(suffixes) >= 3 and suffixes[-2] in _DECOY_EXTENSIONS:
            flags.add("disguised_extension")
    return flags


def inspect_embedded_filenames(contents: bytes) -> EmbeddedFilenameInspection:
    """Inspect name-tree keys and /F, /UF, /DOS, /Mac, /Unix FileSpec names.

    Use the existing bounded attachment discovery graph, which includes
    catalog/page /AF, EmbeddedFiles name trees and FileAttachment annotations.
    Never dereference embedded file streams, fetch URLs, or write attachments.
    """
    try:
        parse_pdf_structure(contents)
        from pypdf import PdfReader
        from pypdf.generic import (
            ArrayObject, ByteStringObject, DictionaryObject, IndirectObject,
            StreamObject, TextStringObject,
        )

        reader = PdfReader(BytesIO(contents), strict=True)
        if reader.is_encrypted:
            raise EmbeddedFilenameInspectionError(BLOCK_MESSAGE)
        specs = _specifications(reader, MAX_ATTACHMENTS)
        references = 0
        total_characters = 0

        def resolve(value):
            nonlocal references
            seen = set()
            while isinstance(value, IndirectObject):
                key = (value.idnum, value.generation)
                if key in seen:
                    raise EmbeddedFilenameInspectionError(BLOCK_MESSAGE)
                seen.add(key)
                references += 1
                if references > MAX_REFERENCES:
                    raise EmbeddedFilenameInspectionError(BLOCK_MESSAGE)
                value = value.get_object()
            return value

        def dictionary(value):
            obj = resolve(value)
            if not isinstance(obj, DictionaryObject) or isinstance(obj, StreamObject):
                raise EmbeddedFilenameInspectionError(BLOCK_MESSAGE)
            return obj

        def array(value):
            obj = resolve(value)
            if not isinstance(obj, ArrayObject):
                raise EmbeddedFilenameInspectionError(BLOCK_MESSAGE)
            return obj

        def filename(value):
            nonlocal total_characters
            obj = resolve(value)
            # ByteStringObject implies undecodable PDF text. Do not guess.
            if isinstance(obj, ByteStringObject) or not isinstance(obj, TextStringObject):
                raise EmbeddedFilenameInspectionError(BLOCK_MESSAGE)
            result = str(obj)
            if not result or len(result) > MAX_FILENAME_CHARACTERS or "\x00" in result:
                raise EmbeddedFilenameInspectionError(BLOCK_MESSAGE)
            total_characters += len(result)
            if total_characters > MAX_TOTAL_FILENAME_CHARACTERS:
                raise EmbeddedFilenameInspectionError(BLOCK_MESSAGE)
            return result

        per_spec = {}
        for spec in specs:
            if spec.get("/Type") not in (None, "/Filespec"):
                raise EmbeddedFilenameInspectionError(BLOCK_MESSAGE)
            if "/EF" not in spec:
                raise EmbeddedFilenameInspectionError(BLOCK_MESSAGE)
            ef = dictionary(spec.raw_get("/EF"))
            if not any(key in ef for key in ("/F", "/UF")):
                raise EmbeddedFilenameInspectionError(BLOCK_MESSAGE)
            strings = [filename(spec.raw_get(key)) for key in
                       ("/F", "/UF", "/DOS", "/Mac", "/Unix") if key in spec]
            if not strings:
                raise EmbeddedFilenameInspectionError(BLOCK_MESSAGE)
            flags = set().union(*(_classify(s) for s in strings))
            if len(set(strings)) > 1:
                flags.add("name_disagreement")
            per_spec[id(spec)] = (flags, strings)

        alias_count = 0
        catalog = dictionary(reader.trailer.raw_get("/Root"))
        if "/Names" in catalog:
            names = dictionary(catalog.raw_get("/Names"))
            if "/EmbeddedFiles" in names:
                pending = [(names.raw_get("/EmbeddedFiles"), 0)]
                seen_trees = set()
                while pending:
                    ref, depth = pending.pop()
                    if depth >= 32 or len(seen_trees) >= MAX_NAME_TREE_NODES:
                        raise EmbeddedFilenameInspectionError(BLOCK_MESSAGE)
                    node = dictionary(ref)
                    marker = id(node)
                    if marker in seen_trees:
                        raise EmbeddedFilenameInspectionError(BLOCK_MESSAGE)
                    seen_trees.add(marker)
                    if "/Names" in node:
                        entries = array(node.raw_get("/Names"))
                        if len(entries) % 2 or len(entries) > MAX_ATTACHMENTS * 2:
                            raise EmbeddedFilenameInspectionError(BLOCK_MESSAGE)
                        for i in range(0, len(entries), 2):
                            alias = filename(entries[i])
                            spec = dictionary(entries[i + 1])
                            info = per_spec.get(id(spec))
                            if info is None:
                                raise EmbeddedFilenameInspectionError(BLOCK_MESSAGE)
                            flags, strings = info
                            flags.update(_classify(alias))
                            if alias not in strings:
                                flags.add("name_disagreement")
                            alias_count += 1
                            if alias_count > MAX_ATTACHMENTS:
                                raise EmbeddedFilenameInspectionError(BLOCK_MESSAGE)
                    if "/Kids" in node:
                        children = array(node.raw_get("/Kids"))
                        if not children or len(children) > MAX_NAME_TREE_NODES:
                            raise EmbeddedFilenameInspectionError(BLOCK_MESSAGE)
                        pending.extend((child, depth + 1) for child in children)
                    if "/Names" not in node and "/Kids" not in node:
                        raise EmbeddedFilenameInspectionError(BLOCK_MESSAGE)

        flags = tuple(sorted(set().union(*(item[0] for item in per_spec.values())))) if per_spec else ()
        return EmbeddedFilenameInspection(
            len(specs), alias_count,
            sum(bool(item[0]) for item in per_spec.values()), flags,
        )
    except EmbeddedFilenameInspectionError:
        raise
    except Exception:
        # Never include strings, parser diagnostics, URLs or document paths.
        raise EmbeddedFilenameInspectionError(BLOCK_MESSAGE) from None
