"""Deterministic, harmless reference PDF corpus for protection regression tests.

All samples are generated in memory; no PDFs from outside the repository,
user files, executable payloads, or real malware signatures are included.
The scanner outcomes in tests are injected fixtures, not claims about actual
malware detection or the currently unimplemented profile engines.
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class ReferencePDF:
    identifier: str
    content: bytes
    simulated_scanner_outcome: str


def _one_page_pdf(label: str) -> bytes:
    """Generate a complete, minimal single-page PDF with valid xref offsets."""
    if not label.isascii() or any(c in label for c in "()\\"):
        raise ValueError("Fixture label must be safe ASCII PDF literal text")
    stream = b"BT /F1 12 Tf 72 720 Td (" + label.encode("ascii") + b") Tj ET\n"
    objects = (
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] "
        b"/Resources << /Font << /F1 5 0 R >> >> /Contents 4 0 R >>",
        b"<< /Length " + str(len(stream)).encode("ascii")
        + b" >>\nstream\n" + stream + b"endstream",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
    )
    data = bytearray(b"%PDF-1.4\n")
    offsets = [0]
    for number, content in enumerate(objects, start=1):
        offsets.append(len(data))
        data.extend(str(number).encode("ascii") + b" 0 obj\n"
                    + content + b"\nendobj\n")
    startxref = len(data)
    data.extend(b"xref\n0 6\n0000000000 65535 f \n")
    for offset in offsets[1:]:
        data.extend(f"{offset:010d} 00000 n \n".encode("ascii"))
    data.extend(b"trailer\n<< /Size 6 /Root 1 0 R >>\nstartxref\n"
                + str(startxref).encode("ascii") + b"\n%%EOF\n")
    return bytes(data)


# The identical ordered collection must be used for EACH of the three
# planned profile IDs. All files are harmless; expected scanner behavior is
# simulated by a stub, not inferred from sample bytes.
REFERENCE_PDFS = (
    ReferencePDF("clean-basic", _one_page_pdf("Clean baseline"), "clean"),
    ReferencePDF("clean-second", _one_page_pdf("Second distinct clean sample"), "clean"),
    ReferencePDF("detected-verdict", _one_page_pdf("Simulated detection verdict"), "detected"),
    ReferencePDF("incomplete-verdict", _one_page_pdf("Simulated incomplete scan"), "incomplete"),
    ReferencePDF("scanner-error", _one_page_pdf("Simulated scanner error"), "failed"),
    ReferencePDF("scanner-timeout", _one_page_pdf("Simulated scanner timeout"), "timeout"),
)


@dataclass(frozen=True)
class InvalidPDFHeader:
    """A harmless header-corrupted PDF with an expected identification status."""

    identifier: str
    content: bytes
    expected_header_status: str


# Only the first nine bytes of the valid baseline are replaced. The entire
# PDF object, xref, trailer and EOF region is shared with the valid corpus;
# none of these samples contains an active payload or downloaded content.
# Keep this collection separate from REFERENCE_PDFS: that existing collection
# must remain exclusively valid and unchanged for profile admission tests.
_INVALID_HEADER_CASES = (
    ("missing-magic", b"NOTPD-1.4", "notPdf"),
    ("wrong-magic", b"%PDX-1.4\n", "notPdf"),
    ("leading-bom", b"\xef\xbb\xbfPDF1.4", "notPdf"),
    ("unsupported-minor-version", b"%PDF-1.8\n", "undetermined"),
    ("unsupported-major-version", b"%PDF-2.1\n", "undetermined"),
    ("nonnumeric-version", b"%PDF-1.x\n", "undetermined"),
    ("nonascii-version", b"%PDF-\xff.4\n", "undetermined"),
    ("space-instead-of-newline", b"%PDF-1.4 ", "undetermined"),
    ("nul-instead-of-newline", b"%PDF-1.4\x00", "undetermined"),
)

INVALID_PDF_HEADERS = tuple(
    InvalidPDFHeader(identifier, corrupted_header + REFERENCE_PDFS[0].content[9:],
                     expected_status)
    for identifier, corrupted_header, expected_status in _INVALID_HEADER_CASES
)
