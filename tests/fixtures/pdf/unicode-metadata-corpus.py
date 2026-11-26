"""Harmless, deterministic PDF documents with unusual Unicode metadata.

Fixture-only module: no files are opened, metadata is trusted, or scanner
verdicts are inferred. Keep these separate from six clean profile baselines.
"""

from dataclasses import dataclass, field
from io import BytesIO

from pypdf import PdfWriter
from pypdf.generic import DecodedStreamObject, NameObject


@dataclass(frozen=True)
class UnicodeMetadataPDF:
    identifier: str
    content: bytes = field(repr=False)
    info: tuple[tuple[str, str], ...] = field(repr=False)
    xmp: tuple[tuple[str, str], ...] = field(repr=False)


def _pdf_with_metadata(info: dict[str, str], *, xmp: bytes = b"",
                       compress_xmp: bool = False) -> bytes:
    """Construct a complete one-page PDF with genuine Info/XMP objects."""
    writer = PdfWriter()
    writer.add_blank_page(width=612, height=792)
    writer.add_metadata({"/" + key: value for key, value in info.items()})
    if xmp:
        stream = DecodedStreamObject()
        stream.set_data(xmp)
        stream[NameObject("/Type")] = NameObject("/Metadata")
        stream[NameObject("/Subtype")] = NameObject("/XML")
        if compress_xmp:
            stream = stream.flate_encode()
        writer._root_object[NameObject("/Metadata")] = writer._add_object(stream)
    output = BytesIO()
    writer.write(output)
    return output.getvalue()


def _xmp(title: str, author: str) -> bytes:
    """Known literal strings below contain no XML markup or metacharacters."""
    return (
        '<x:xmpmeta xmlns:x="adobe:ns:meta/">'
        '<rdf:RDF xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#"'
        ' xmlns:dc="http://purl.org/dc/elements/1.1/">'
        '<rdf:Description><dc:title><rdf:Alt>'
        '<rdf:li xml:lang="x-default">' + title + '</rdf:li>'
        '</rdf:Alt></dc:title><dc:creator><rdf:Seq>'
        '<rdf:li>' + author + '</rdf:li>'
        '</rdf:Seq></dc:creator></rdf:Description></rdf:RDF></x:xmpmeta>'
    ).encode("utf-8")


def _sample(identifier: str, info: dict[str, str], *,
            xmp_title: str = "", xmp_author: str = "",
            compressed: bool = False) -> UnicodeMetadataPDF:
    xmp = _xmp(xmp_title, xmp_author) if xmp_title else b""
    return UnicodeMetadataPDF(
        identifier,
        _pdf_with_metadata(info, xmp=xmp, compress_xmp=compressed),
        tuple(sorted(((key[0].lower() + key[1:], value)
                      for key, value in info.items()))),
        tuple(sorted((("title", xmp_title), ("author", xmp_author)))) if xmp else (),
    )


# Use true Unicode, not escaped ASCII metadata. pypdf encodes PDF Info strings
# using PDF string syntax (UTF-16BE with BOM when needed), while XMP is UTF-8.
# Combining marks, bidirectional controls, variation selectors and ZWJ are
# intentionally retained as data, never interpreted as commands or identities.
UNICODE_METADATA_PDFS = (
    _sample("multilingual-info", {
        "Title": "Καλημέρα 世界 مرحبا हिंदी 🚀",
        "Author": "Zoë Nguyễn",
        "Subject": "Українська עברית",
    }),
    _sample("normalization-forms", {
        "Title": "Café Ångström",  # precomposed
        "Author": "Cafe\u0301 A\u030angstro\u0308m",  # decomposed
    }),
    _sample("bidirectional-and-invisible", {
        "Title": "Invoice \u202e123\u202c سلام",
        "Keywords": "zero\u200bwidth, family 👩🏽\u200d💻, heart ❤️",
    }),
    _sample("xmp-multilingual", {
        "Title": "Info title differs from XMP 📜",
        "Author": "Info auteur François",
    }, xmp_title="東京 — café 🍵", xmp_author="Miyuki 美由紀"),
    _sample("xmp-compressed-combining", {
        "Title": "Emoji and combining marks 👩🏽\u200d💻",
    }, xmp_title="A\u030angstro\u0308m 👩🏽\u200d💻", xmp_author="עברית عربية",
       compressed=True),
)
