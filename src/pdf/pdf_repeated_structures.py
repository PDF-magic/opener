"""Report suspiciously repeated PDF object shapes as passive review evidence.

This optional Enhanced-stage helper only inspects bounded in-memory PDF
structure. It does not decode stream payloads, execute content, open paths,
change the active scanner gate, or authorize opening.
"""

from collections import Counter
from dataclasses import dataclass
from hashlib import sha256
from io import BytesIO
import re

from pdf_structure_parser import parse_pdf_structure

MAX_REPEATED_OBJECTS = 4096
MAX_REPEATED_STRUCTURE_NODES = 65536
MAX_REPEATED_STRUCTURE_DEPTH = 64
MIN_REPEATED_GROUP = 32
DOMINANT_REPEATED_GROUP = 128
_ERROR = "PDF repeated structures could not be verified; opening was stopped."
_MAX_OBJECT_NUMBER = 2 ** 31 - 1


class PDFRepeatedStructuresError(RuntimeError):
    """Fixed, path-free error for incomplete structural repetition evidence."""


def _is_suspicious(largest_group: int, repeated_count: int, inspected_count: int) -> bool:
    """Require either extreme repetition or a large share of inspected shapes."""
    return largest_group >= DOMINANT_REPEATED_GROUP or (
        largest_group >= MIN_REPEATED_GROUP and repeated_count * 4 >= inspected_count
    )


@dataclass(frozen=True)
class PDFRepeatedStructures:
    """Bounded repetition counts; no PDF content and no opening authorization."""

    object_count: int
    inspected_structure_count: int
    repeated_structure_groups: int
    repeated_object_count: int
    largest_repeated_group: int
    suspicious_repetition: bool
    permits_open: bool = False

    def __post_init__(self):
        integers = (
            self.object_count, self.inspected_structure_count,
            self.repeated_structure_groups, self.repeated_object_count,
            self.largest_repeated_group,
        )
        if (
            any(type(value) is not int for value in integers)
            or not 1 <= self.object_count <= MAX_REPEATED_OBJECTS
            or not 0 <= self.inspected_structure_count <= self.object_count
            or not 0 <= self.repeated_structure_groups <= self.repeated_object_count // 2
            or not 0 <= self.repeated_object_count <= self.inspected_structure_count
            or not 0 <= self.largest_repeated_group <= self.repeated_object_count
            or (self.repeated_structure_groups == 0 and (
                self.repeated_object_count != 0 or self.largest_repeated_group != 0
            ))
            or (self.repeated_structure_groups > 0 and self.largest_repeated_group < 2)
            or type(self.suspicious_repetition) is not bool
            or self.suspicious_repetition != _is_suspicious(
                self.largest_repeated_group, self.repeated_object_count,
                self.inspected_structure_count,
            )
            or self.permits_open is not False
        ):
            raise ValueError("Invalid repeated-structure evidence cannot authorize opening")

    def to_dict(self) -> dict[str, str | int | bool]:
        """Return detached, stable metadata with no PDF-controlled strings."""
        return {
            "schemaVersion": 1,
            "objectCount": self.object_count,
            "inspectedStructureCount": self.inspected_structure_count,
            "repeatedStructureGroups": self.repeated_structure_groups,
            "repeatedObjectCount": self.repeated_object_count,
            "largestRepeatedGroup": self.largest_repeated_group,
            "suspiciousRepetition": self.suspicious_repetition,
            "authorizesOpen": False,
        }


def _shape(value, generic, depth: int, budget: list[int]):
    """Normalize values to structural types; references are never followed."""
    budget[0] += 1
    if budget[0] > MAX_REPEATED_STRUCTURE_NODES or depth > MAX_REPEATED_STRUCTURE_DEPTH:
        raise PDFRepeatedStructuresError(_ERROR)

    if isinstance(value, generic["IndirectObject"]):
        return ("reference",)
    if isinstance(value, generic["StreamObject"]):
        return ("stream", _shape_dictionary(value, generic, depth, budget))
    if isinstance(value, generic["DictionaryObject"]):
        return _shape_dictionary(value, generic, depth, budget)
    if isinstance(value, generic["ArrayObject"]):
        return ("array", tuple(_shape(item, generic, depth + 1, budget) for item in value))
    if isinstance(value, generic["NameObject"]):
        return ("name", str(value))
    if isinstance(value, generic["BooleanObject"]):
        return ("boolean",)
    if isinstance(value, (generic["NumberObject"], generic["FloatObject"])):
        return ("number",)
    if isinstance(value, (generic["TextStringObject"], generic["ByteStringObject"])):
        return ("string",)
    if isinstance(value, generic["NullObject"]) or value is None:
        return ("null",)
    if isinstance(value, bool):
        return ("boolean",)
    if isinstance(value, (int, float)):
        return ("number",)
    if isinstance(value, (str, bytes)):
        return ("string",)
    return ("other", type(value).__name__)


def _shape_dictionary(value, generic, depth: int, budget: list[int]):
    items = []
    for key in sorted(value.keys(), key=str):
        key_name = str(key)
        items.append((key_name, _shape(value.raw_get(key_name), generic, depth + 1, budget)))
    return ("dictionary", tuple(items))


def inspect_pdf_repeated_structures(contents: bytes) -> PDFRepeatedStructures:
    """Find recurring non-page dictionary/array shapes without decoding streams.

    Values are normalized to their structural types (and names remain names),
    while strings and numbers are never returned. Stream payloads and ordinary
    /Page and /Pages dictionaries are excluded to avoid treating page count or
    repeated content streams as suspicious by themselves. Thresholds are review
    signals only; repeated structures can occur in legitimate documents.
    """
    try:
        parse_pdf_structure(contents)
    except Exception:
        raise PDFRepeatedStructuresError(_ERROR) from None

    try:
        from pypdf import PdfReader
        from pypdf.generic import (
            ArrayObject, BooleanObject, ByteStringObject, DictionaryObject,
            FloatObject, IndirectObject, NameObject, NullObject, NumberObject,
            StreamObject, TextStringObject,
        )

        reader = PdfReader(BytesIO(contents), strict=True)
        if reader.is_encrypted or reader.xref_objStm:
            raise PDFRepeatedStructuresError(_ERROR)
        generic = {
            "ArrayObject": ArrayObject,
            "BooleanObject": BooleanObject,
            "ByteStringObject": ByteStringObject,
            "DictionaryObject": DictionaryObject,
            "FloatObject": FloatObject,
            "IndirectObject": IndirectObject,
            "NameObject": NameObject,
            "NullObject": NullObject,
            "NumberObject": NumberObject,
            "StreamObject": StreamObject,
            "TextStringObject": TextStringObject,
        }

        indexed = []
        seen = set()
        for generation, records in reader.xref.items():
            if type(generation) is not int or not 0 <= generation <= 65535:
                raise PDFRepeatedStructuresError(_ERROR)
            for number, offset in records.items():
                if number == 0:
                    continue
                identity = (number, generation)
                if (
                    type(number) is not int or not 1 <= number <= _MAX_OBJECT_NUMBER
                    or type(offset) is not int or not 0 < offset < len(contents)
                    or identity in seen
                ):
                    raise PDFRepeatedStructuresError(_ERROR)
                header = re.match(
                    rb"\s*%d\s+%d\s+obj\b" % (number, generation),
                    contents[offset:offset + 80],
                )
                if header is None:
                    raise PDFRepeatedStructuresError(_ERROR)
                seen.add(identity)
                indexed.append(identity)
                if len(indexed) > MAX_REPEATED_OBJECTS:
                    raise PDFRepeatedStructuresError(_ERROR)
        if not indexed:
            raise PDFRepeatedStructuresError(_ERROR)

        counts = Counter()
        inspected = 0
        budget = [0]
        for number, generation in indexed:
            value = reader.get_object(IndirectObject(number, generation, reader))
            if value is None or isinstance(value, StreamObject):
                continue
            if isinstance(value, DictionaryObject) and "/Type" in value:
                kind = value.raw_get("/Type")
                if isinstance(kind, NameObject) and str(kind) in ("/Page", "/Pages"):
                    continue
            if not isinstance(value, (DictionaryObject, ArrayObject)):
                continue
            shape = _shape(value, generic, 0, budget)
            signature = sha256(repr(shape).encode("utf-8", "backslashreplace")).digest()
            counts[signature] += 1
            inspected += 1

        repeats = [count for count in counts.values() if count >= 2]
        repeated_count = sum(repeats)
        largest = max(repeats, default=0)
        suspicious = _is_suspicious(largest, repeated_count, inspected)
        return PDFRepeatedStructures(
            object_count=len(indexed),
            inspected_structure_count=inspected,
            repeated_structure_groups=len(repeats),
            repeated_object_count=repeated_count,
            largest_repeated_group=largest,
            suspicious_repetition=suspicious,
        )
    except PDFRepeatedStructuresError:
        raise
    except Exception:
        # Parser errors may contain PDF strings or paths; expose only a fixed code.
        raise PDFRepeatedStructuresError(_ERROR) from None
