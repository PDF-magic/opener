"""Report unusual PDF indirect-object counts as passive Enhanced evidence.

This stage observes cardinality anomalies, not malware or a scan verdict.
It does not resolve unneeded objects, decode streams, execute actions, open
filesystem paths, change the ClamAV gate, or authorize opening.
"""

from dataclasses import dataclass, field
from io import BytesIO

from pdf_structure_parser import PDFStructureParseError, parse_pdf_structure


MAX_INDEXED_OBJECTS = 4096
MAX_OBJECT_NUMBER = 2 ** 31 - 1
HIGH_OBJECT_COUNT = 1024
HIGH_OBJECTS_PER_PAGE = 128
SPARSE_OBJECT_NUMBER_FLOOR = 256
SPARSE_OBJECT_NUMBER_FACTOR = 8
_ANOMALIES = frozenset((
    "high_object_count", "high_objects_per_page", "sparse_object_ids",
))
_ERROR = "PDF object counts could not be fully inspected; opening was stopped."


class PDFUnusualObjectCountError(RuntimeError):
    """Fixed, path-free error for uninspectable object-count evidence."""


def _anomalies(total: int, pages: int, maximum_number: int) -> tuple[str, ...]:
    return tuple(sorted(
        code for code, unusual in (
            ("high_object_count", total >= HIGH_OBJECT_COUNT),
            ("high_objects_per_page", total > pages * HIGH_OBJECTS_PER_PAGE),
            ("sparse_object_ids", maximum_number >= max(
                SPARSE_OBJECT_NUMBER_FLOOR,
                total * SPARSE_OBJECT_NUMBER_FACTOR,
            )),
        ) if unusual
    ))


@dataclass(frozen=True)
class PDFUnusualObjectCounts:
    """Bounded, known-code evidence; absence of flags is not a clean verdict."""

    object_count: int
    page_count: int
    highest_object_number: int
    anomaly_codes: tuple[str, ...]
    permits_open: bool = field(default=False, init=False)

    def __post_init__(self):
        if (
            type(self.object_count) is not int
            or not 1 <= self.object_count <= MAX_INDEXED_OBJECTS
            or type(self.page_count) is not int
            or not 1 <= self.page_count <= 1024
            or type(self.highest_object_number) is not int
            or not self.object_count <= self.highest_object_number <= MAX_OBJECT_NUMBER
            or type(self.anomaly_codes) is not tuple
            or self.anomaly_codes != _anomalies(
                self.object_count, self.page_count, self.highest_object_number
            )
            or self.permits_open is not False
        ):
            raise ValueError("Invalid object-count evidence cannot authorize opening")

    @property
    def has_unusual_counts(self) -> bool:
        return bool(self.anomaly_codes)

    def to_dict(self) -> dict:
        """Only counts and fixed anomaly names; no PDF-provided text or paths."""
        return {
            "schemaVersion": 1,
            "objectCount": self.object_count,
            "pageCount": self.page_count,
            "highestObjectNumber": self.highest_object_number,
            "anomalyCodes": list(self.anomaly_codes),
            "authorizesOpen": False,
        }


def inspect_pdf_unusual_object_counts(contents: bytes) -> PDFUnusualObjectCounts:
    """Count active indirect objects and flag conservative density anomalies.

    Supports traditional xref tables. Compressed-object xref streams must be
    independently supported before they can be counted correctly; refusing
    them avoids false-low counts. Thresholds signal review, not maliciousness.
    """
    try:
        structure = parse_pdf_structure(contents)
    except PDFStructureParseError:
        raise PDFUnusualObjectCountError(_ERROR) from None

    try:
        from pypdf import PdfReader
    except (ImportError, OSError):
        raise PDFUnusualObjectCountError(_ERROR) from None

    try:
        reader = PdfReader(BytesIO(contents), strict=True)
        if reader.is_encrypted or reader.xref_objStm:
            raise PDFUnusualObjectCountError(_ERROR)
        count = 0
        maximum = 0
        seen = set()
        for generation, entries in reader.xref.items():
            if type(generation) is not int or not 0 <= generation <= 65535:
                raise PDFUnusualObjectCountError(_ERROR)
            for number, offset in entries.items():
                if number == 0:
                    continue
                if (
                    type(number) is not int
                    or type(offset) is not int
                    or not 1 <= number <= MAX_OBJECT_NUMBER
                    or not 0 < offset < len(contents)
                    or (number, generation) in seen
                ):
                    raise PDFUnusualObjectCountError(_ERROR)
                seen.add((number, generation))
                count += 1
                maximum = max(maximum, number)
                if count > MAX_INDEXED_OBJECTS:
                    raise PDFUnusualObjectCountError(_ERROR)

        size = reader.trailer.raw_get("/Size")
        if (
            not isinstance(size, int)
            or isinstance(size, bool)
            or size <= maximum
            or not count
        ):
            raise PDFUnusualObjectCountError(_ERROR)

        return PDFUnusualObjectCounts(
            object_count=count,
            page_count=structure.page_count,
            highest_object_number=maximum,
            anomaly_codes=_anomalies(count, structure.page_count, maximum),
        )
    except PDFUnusualObjectCountError:
        raise
    except Exception:
        # Never expose PDF parser error messages containing document text.
        raise PDFUnusualObjectCountError(_ERROR) from None
