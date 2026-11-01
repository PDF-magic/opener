"""Harmless malformed classic-xref PDFs for security regression tests.

Derived only from the repository's valid reference PDF. Fixtures stay in
memory, contain no user documents or active content, and never represent
antivirus detections or permission to open a PDF.
"""

from dataclasses import dataclass

from reference_pdf_collection import REFERENCE_PDFS


@dataclass(frozen=True)
class MalformedXRefPDF:
    identifier: str
    content: bytes


def _build_malformed_xref_pdfs() -> tuple[MalformedXRefPDF, ...]:
    pristine = next(sample.content for sample in REFERENCE_PDFS
                    if sample.identifier == "clean-basic")
    prefix, tail = pristine.split(b"xref\n0 6\n", 1)
    entries, trailer = tail.split(b"trailer\n", 1)
    rows = entries.splitlines(keepends=True)
    if (len(rows) != 6 or not rows[0].endswith(b"65535 f \n")
            or not rows[1].endswith(b"00000 n \n")
            or not rows[2].endswith(b"00000 n \n")):
        raise AssertionError("The canonical PDF xref table changed")

    def fixture(identifier: str, replacement_rows: list[bytes],
                subsection: bytes = b"0 6") -> MalformedXRefPDF:
        return MalformedXRefPDF(
            identifier,
            prefix + b"xref\n" + subsection + b"\n"
            + b"".join(replacement_rows) + b"trailer\n" + trailer,
        )

    return (
        # The first in-use entry points outside the source bytes.
        fixture("xref-out-of-bounds-offset", [
            rows[0], b"9999999999" + rows[1][10:], *rows[2:],
        ]),
        # Two in-use records target the same object, not their own headers.
        fixture("xref-conflicting-object-offsets", [
            rows[0], rows[2][:10] + rows[1][10:], *rows[2:],
        ]),
        # Generation 1 in the xref conflicts with the real '1 0 obj' header.
        fixture("xref-generation-mismatch", [
            rows[0], rows[1][:11] + b"00001" + rows[1][16:], *rows[2:],
        ]),
        # The subsection declares an entry that does not exist.
        fixture("xref-overdeclared-subsection", rows, subsection=b"0 7"),
        # A nonnumeric entry count invalidates the subsection header.
        fixture("xref-nonnumeric-subsection", rows, subsection=b"0 six"),
        # The last entry is missing even though the subsection still claims six.
        fixture("xref-truncated-entry-table", rows[:-1]),
    )


MALFORMED_XREF_PDFS = _build_malformed_xref_pdfs()
