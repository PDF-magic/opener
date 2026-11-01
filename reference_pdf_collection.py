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
class IncorrectlyNamedFile:
    """Inert real PDF or non-PDF bytes under a deliberately misleading name."""

    filename: str
    content: bytes
    is_pdf: bool


# opener-1028: filename extensions are not evidence of PDF format. Keeping
# these separate from REFERENCE_PDFS preserves the stable six-profile corpus.
# Tests materialize each file only inside a disposable temporary directory.
INCORRECTLY_NAMED_FILES = (
    IncorrectlyNamedFile("real-pdf.txt", REFERENCE_PDFS[0].content, True),
    IncorrectlyNamedFile("real-pdf.png", REFERENCE_PDFS[1].content, True),
    IncorrectlyNamedFile("real-pdf.pdf.txt", REFERENCE_PDFS[0].content, True),
    IncorrectlyNamedFile("real-pdf-no-extension", REFERENCE_PDFS[1].content, True),
    IncorrectlyNamedFile("real-pdf.PDF", REFERENCE_PDFS[0].content, True),
    IncorrectlyNamedFile("plain-text.pdf", b"Harmless text, not a PDF.\n", False),
    IncorrectlyNamedFile("png-header.pdf", b"\x89PNG\r\n\x1a\n" + bytes(16), False),
    IncorrectlyNamedFile(
        "embedded-pdf-header.pdf", b"Harmless non-PDF prefix\n%PDF-1.4\n", False
    ),
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


def _append_incremental_revision(original: bytes, changes: tuple, *,
                                 size: int, include_info: bool = False) -> bytes:
    """Append a genuine PDF xref-table revision without rewriting earlier bytes.

    Changes are fixed, harmless fixture objects. Each revision has its own
    startxref and /Prev link so historical objects remain available to tests.
    """
    previous = int(original.rsplit(b"startxref\n", 1)[1].splitlines()[0])
    data = bytearray(original)
    entries = []
    for number, payload in changes:
        entries.append((number, len(data)))
        data.extend(f"{number} 0 obj\n".encode("ascii")
                    + payload + b"\nendobj\n")
    startxref = len(data)
    data.extend(b"xref\n")
    for number, offset in sorted(entries):
        data.extend(f"{number} 1\n{offset:010d} 00000 n \n".encode("ascii"))
    data.extend(f"trailer\n<< /Size {size} /Root 1 0 R /Prev {previous}".encode("ascii"))
    if include_info:
        data.extend(b" /Info 6 0 R")
    data.extend(f" >>\nstartxref\n{startxref}\n%%EOF\n".encode("ascii"))
    return bytes(data)


# Separate from REFERENCE_PDFS: existing profile-baseline tests require those
# six PDFs to have exactly one revision. These added documents exercise real
# incremental updates, not malicious contents or actual scanner verdicts.
_INCREMENTAL_BASE = _one_page_pdf("Incremental reference")
_INCREMENTAL_METADATA = _append_incremental_revision(
    _INCREMENTAL_BASE,
    ((6, b"<< /Title (Inert metadata revision) >>"),),
    size=7,
    include_info=True,
)
_INCREMENTAL_FONT = _append_incremental_revision(
    _INCREMENTAL_BASE,
    ((5, b"<< /Type /Font /Subtype /Type1 /BaseFont /Courier >>"),),
    size=6,
)
INCREMENTAL_REFERENCE_PDFS = (
    ReferencePDF("incremental-added-metadata", _INCREMENTAL_METADATA, "clean"),
    ReferencePDF("incremental-replaced-font", _INCREMENTAL_FONT, "clean"),
    ReferencePDF(
        "incremental-two-updates",
        _append_incremental_revision(
            _INCREMENTAL_METADATA,
            ((5, b"<< /Type /Font /Subtype /Type1 /BaseFont /Courier >>"),),
            size=7,
            include_info=True,
        ),
        "clean",
    ),
)
