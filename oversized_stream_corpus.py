"""Inert, deterministic PDFs with oversized embedded streams (opener-1042).

The corpus is generated in memory, not downloaded or executed. These are
parser/scanner test inputs, never clean verdicts or permissions to open PDFs.
Keep them separate from the six shared protection-profile reference PDFs.
"""

from dataclasses import dataclass
from io import BytesIO

from pypdf import PdfWriter
from pypdf.generic import DecodedStreamObject, DictionaryObject, NameObject, NumberObject


STREAM_LIMIT = 1024 * 1024


@dataclass(frozen=True)
class OversizedStreamPDF:
    identifier: str
    content: bytes
    expected_large_encoded: int
    expected_large_decoded: int
    expected_high_expansion: int
    expected_large_declared: int


def _embedded_pdf(payload: bytes, *, compressed: bool = False,
                  declared_size: int | None = None, orphan: bool = False) -> bytes:
    """Write a complete one-page PDF with a real embedded-file stream."""
    writer = PdfWriter()
    writer.add_blank_page(width=200, height=200)
    if orphan:
        stream = DecodedStreamObject()
        stream.set_data(payload)
        stream[NameObject("/Type")] = NameObject("/EmbeddedFile")
        writer._add_object(stream)
    else:
        writer.add_attachment("synthetic-fixture.bin", payload)
        spec = writer._root_object["/Names"]["/EmbeddedFiles"]["/Names"][1].get_object()
        stream = spec["/EF"]["/F"].get_object()
        if compressed:
            zipped = stream.flate_encode()
            stream._data = zipped._data
            stream[NameObject("/Filter")] = NameObject("/FlateDecode")
        if declared_size is not None:
            stream[NameObject("/Params")] = DictionaryObject({
                NameObject("/Size"): NumberObject(declared_size),
            })
    output = BytesIO()
    writer.write(output)
    return output.getvalue()


# Distinct cases: physical stream size, decompressed payload size, unreferenced
# /EmbeddedFile objects, and the separately declared attachment size. None
# carries active actions, executable content, network locations or user data.
OVERSIZED_STREAM_PDFS = (
    OversizedStreamPDF(
        "oversized-raw-attachment",
        _embedded_pdf(b"A" * (STREAM_LIMIT + 1)), 1, 1, 0, 0,
    ),
    OversizedStreamPDF(
        "oversized-flate-attachment",
        _embedded_pdf(b"B" * (2 * STREAM_LIMIT + 1), compressed=True), 0, 1, 1, 0,
    ),
    OversizedStreamPDF(
        "oversized-orphan-embedded-stream",
        _embedded_pdf(b"C" * (STREAM_LIMIT + 1), orphan=True), 1, 1, 0, 0,
    ),
    OversizedStreamPDF(
        "oversized-declared-attachment",
        _embedded_pdf(b"harmless fixture", declared_size=4 * STREAM_LIMIT), 0, 0, 0, 1,
    ),
)
