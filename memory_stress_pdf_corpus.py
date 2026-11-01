"""Deterministic, inert PDFs that pressure bounded structure-inspection memory.

Fixtures are constructed only when requested; no large binaries, downloaded
content, active PDF actions, or scanner decisions are embedded in the corpus.
Every stream is individually within the decoded-stream budget; the cumulative
case deliberately exceeds the separate aggregate budget.
"""

from dataclasses import dataclass
from typing import Callable
import zlib


REFERENCE_FANOUT = 50_000
DENSE_OBJECT_COUNT = 4_097
DECODED_BYTES_PER_STREAM = 7 * 1024 * 1024
AGGREGATE_STREAM_COUNT = 5


@dataclass(frozen=True)
class MemoryStressPDF:
    identifier: str
    generate: Callable[[], bytes]


def _pdf(objects: tuple[bytes, ...]) -> bytes:
    """Build a complete one-page PDF with real, correctly offset xref entries."""
    document = bytearray(b"%PDF-1.4\n")
    offsets = []
    for number, body in enumerate(objects, 1):
        offsets.append(len(document))
        document.extend(f"{number} 0 obj\n".encode("ascii"))
        document.extend(body)
        document.extend(b"\nendobj\n")
    startxref = len(document)
    document.extend(f"xref\n0 {len(objects) + 1}\n0000000000 65535 f \n".encode("ascii"))
    for offset in offsets:
        document.extend(f"{offset:010d} 00000 n \n".encode("ascii"))
    document.extend(
        f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\n"
        f"startxref\n{startxref}\n%%EOF\n".encode("ascii")
    )
    return bytes(document)


def _base_objects(catalog_extra: bytes = b"") -> tuple[bytes, ...]:
    return (
        b"<< /Type /Catalog /Pages 2 0 R " + catalog_extra + b">>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 200 200] >>",
    )


def reference_fanout_pdf() -> bytes:
    """A tiny-on-disk PDF with 50k inert references in a catalog array."""
    return _pdf(_base_objects(
        b"/MemoryProbe [" + b"3 0 R " * REFERENCE_FANOUT + b"] "
    ))


def dense_object_table_pdf() -> bytes:
    """Index one object beyond the 4096-object inspection budget."""
    return _pdf(_base_objects() + (b"null",) * (DENSE_OBJECT_COUNT - 3))


def aggregate_flate_pdf() -> bytes:
    """Five individually bounded Flate streams expand to 35 MiB in total."""
    compressed = zlib.compress(b"M" * DECODED_BYTES_PER_STREAM, level=9)
    stream = (
        b"<< /Filter /FlateDecode /Length "
        + str(len(compressed)).encode("ascii")
        + b" >>\nstream\n" + compressed + b"\nendstream"
    )
    # Unreferenced streams still belong to the indexed document and must be
    # included in the aggregate memory budget, not silently skipped.
    return _pdf(_base_objects() + (stream,) * AGGREGATE_STREAM_COUNT)


MEMORY_STRESS_PDFS = (
    MemoryStressPDF("high-reference-fanout", reference_fanout_pdf),
    MemoryStressPDF("dense-object-table", dense_object_table_pdf),
    MemoryStressPDF("aggregate-flate-expansion", aggregate_flate_pdf),
)
