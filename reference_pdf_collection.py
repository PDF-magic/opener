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

DEEP_OBJECT_REFERENCE_DEPTH = 96


def _deeply_nested_object_references_pdf():
    """Build a valid one-page PDF with a 96-hop, acyclic indirect-object chain.

    The chain is linked from a nonstandard, inert catalog key; it does not
    alter the page tree or carry actions, scripts, attachments, or executables.
    Each object has its own cross-reference entry and a deterministic index.
    """
    stream = b"BT /F1 12 Tf 72 720 Td (Nested references fixture) Tj ET\n"
    objects = {
        1: b"<< /Type /Catalog /Pages 2 0 R /DeepReference 6 0 R >>",
        2: b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        3: (b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] "
            b"/Resources << /Font << /F1 5 0 R >> >> /Contents 4 0 R >>"),
        4: (b"<< /Length " + str(len(stream)).encode("ascii")
            + b" >>\nstream\n" + stream + b"endstream"),
        5: b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
    }
    for index in range(DEEP_OBJECT_REFERENCE_DEPTH):
        number = index + 6
        following = (f"{number + 1} 0 R" if index + 1 < DEEP_OBJECT_REFERENCE_DEPTH
                     else "null")
        objects[number] = (
            f"<< /Index {index} /Next {following} >>".encode("ascii")
        )

    document = bytearray(b"%PDF-1.4\n")
    offsets = {}
    for number, value in sorted(objects.items()):
        offsets[number] = len(document)
        document.extend(f"{number} 0 obj\n".encode("ascii") + value + b"\nendobj\n")
    xref = len(document)
    document.extend(f"xref\n0 {len(objects) + 1}\n0000000000 65535 f \n".encode("ascii"))
    for number in range(1, len(objects) + 1):
        document.extend(f"{offsets[number]:010d} 00000 n \n".encode("ascii"))
    document.extend(
        f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\n"
        f"startxref\n{xref}\n%%EOF\n".encode("ascii")
    )
    return bytes(document)


# Keep the six shared profile-baseline samples unchanged. Security corpus
# cases are separate because they exercise specialized parser boundaries.
SECURITY_REFERENCE_PDFS = (
    ReferencePDF(
        "deeply-nested-object-references",
        _deeply_nested_object_references_pdf(),
        "clean",
    ),
)
