"""Deterministic, inert large PDF documents for the security test corpus.

These are on-demand test fixtures, not scanner verdicts or permission to open.
They never read user data, access the network, or contain active PDF actions.
"""

from dataclasses import dataclass


MIB = 1024 * 1024
LARGE_PDF_MIN_BYTES = 16 * MIB


@dataclass(frozen=True)
class LargeValidPDFCase:
    identifier: str
    page_count: int
    padding_per_page: int


# Two independent stress shapes: a single very large content stream and a
# multipage document with distinct, actual page-content streams. Both exceed
# the optional structure analyzer's 16 MiB admission bound on purpose.
LARGE_VALID_PDF_CASES = (
    LargeValidPDFCase("single-large-stream", 1, 17 * MIB),
    LargeValidPDFCase("many-large-pages", 256, 64 * 1024),
)


def build_large_valid_pdf(case: LargeValidPDFCase) -> bytes:
    """Return a complete PDF 1.4 with real streams and exact xref offsets.

    Padding is harmless PDF content-stream whitespace, *inside* the declared
    /Length, never fake bytes appended after %%EOF. No external resources,
    actions, embedded files, scripts or decoding filters are involved.
    """
    if case not in LARGE_VALID_PDF_CASES:
        raise ValueError("Only fixed, reviewed security-corpus cases are allowed")

    pages = case.page_count
    font_number = 3 + 2 * pages
    kids = b" ".join(f"{3 + 2 * i} 0 R".encode("ascii") for i in range(pages))
    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [" + kids + b"] /Count "
        + str(pages).encode("ascii") + b" >>",
    ]
    for i in range(pages):
        page_number = 3 + 2 * i
        stream_number = page_number + 1
        label = f"Large valid PDF page {i + 1}"
        content = (
            b"BT /F1 12 Tf 72 720 Td (" + label.encode("ascii")
            + b") Tj ET\n" + b" " * case.padding_per_page
        )
        objects.append(
            b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] "
            + b"/Resources << /Font << /F1 " + str(font_number).encode("ascii")
            + b" 0 R >> >> /Contents " + str(stream_number).encode("ascii")
            + b" 0 R >>"
        )
        objects.append(
            b"<< /Length " + str(len(content)).encode("ascii")
            + b" >>\nstream\n" + content + b"\nendstream"
        )
    objects.append(b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>")

    document = bytearray(b"%PDF-1.4\n")
    offsets = [0]
    for number, value in enumerate(objects, start=1):
        offsets.append(len(document))
        document.extend(f"{number} 0 obj\n".encode("ascii"))
        document.extend(value)
        document.extend(b"\nendobj\n")

    xref = len(document)
    document.extend(f"xref\n0 {len(offsets)}\n0000000000 65535 f \n".encode("ascii"))
    for offset in offsets[1:]:
        document.extend(f"{offset:010d} 00000 n \n".encode("ascii"))
    document.extend(
        f"trailer\n<< /Size {len(offsets)} /Root 1 0 R >>\n"
        f"startxref\n{xref}\n%%EOF\n".encode("ascii")
    )
    return bytes(document)
