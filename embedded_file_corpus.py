"""Deterministic, inert PDF documents containing embedded file streams.

The corpus exercises four legitimate attachment discovery locations. Samples
exist only in memory, contain harmless text, and are never opened or executed.
They do not express ClamAV verdicts or authorize PDF opening.
"""

from dataclasses import dataclass
from io import BytesIO

from pypdf import PdfWriter
from pypdf.generic import ArrayObject, DictionaryObject, NameObject


@dataclass(frozen=True)
class EmbeddedFilePDF:
    identifier: str
    content: bytes
    location: str
    attachments: tuple[tuple[str, bytes], ...]


def _document_with_embedded_files(
    location: str, attachments: tuple[tuple[str, bytes], ...]
) -> bytes:
    """Write genuine /EmbeddedFile streams without adding active PDF actions."""
    if not attachments:
        raise ValueError("Embedded-file fixtures require an attachment")
    writer = PdfWriter()
    writer.add_blank_page(width=612, height=792)
    for name, payload in attachments:
        writer.add_attachment(name, payload)

    catalog = writer._root_object
    specifications = catalog["/Names"]["/EmbeddedFiles"]["/Names"][1::2]
    if location != "name-tree":
        del catalog[NameObject("/Names")]
        if location == "catalog-associated":
            catalog[NameObject("/AF")] = ArrayObject(specifications)
        elif location == "page-associated":
            writer.pages[0][NameObject("/AF")] = ArrayObject(specifications)
        elif location == "annotation":
            writer.pages[0][NameObject("/Annots")] = ArrayObject([
                writer._add_object(DictionaryObject({
                    NameObject("/Subtype"): NameObject("/FileAttachment"),
                    NameObject("/FS"): spec,
                })) for spec in specifications
            ])
        else:
            raise ValueError("Unknown embedded-file fixture location")

    output = BytesIO()
    writer.write(output)
    return output.getvalue()


# Keep away from the six clean reference PDFs: those baseline documents must
# not gain attachments or acquire different scanner/profile expectations.
_CASES = (
    ("name-tree-multiple", "name-tree", (
        ("note.txt", b"Inert PDF attachment fixture.\n"),
        ("values.csv", b"item,count\nsample,1\n"),
    )),
    ("catalog-associated-only", "catalog-associated", (
        ("catalog.txt", b"Inert catalog-associated attachment.\n"),
    )),
    ("page-associated-only", "page-associated", (
        ("page.txt", b"Inert page-associated attachment.\n"),
    )),
    ("annotation-only", "annotation", (
        ("annotation.txt", b"Inert annotation attachment.\n"),
    )),
)

EMBEDDED_FILE_PDFS = tuple(
    EmbeddedFilePDF(identifier, _document_with_embedded_files(location, attachments),
                    location, attachments)
    for identifier, location, attachments in _CASES
)
