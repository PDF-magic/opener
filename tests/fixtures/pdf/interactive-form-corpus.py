"""Deterministic, inert interactive AcroForm documents for security corpus tests.

These PDF bytes are never an opening authorization or antivirus verdict.
Fixtures are separate from the six shared clean-reference PDF documents.
"""

from dataclasses import dataclass
from io import BytesIO

from pypdf import PdfWriter
from pypdf.generic import (
    ArrayObject, BooleanObject, DecodedStreamObject, DictionaryObject,
    NameObject, NumberObject, TextStringObject,
)


@dataclass(frozen=True)
class InteractiveFormPDF:
    identifier: str
    content: bytes
    field_type: str
    field_value: str


def _appearance(writer, *, checked=False):
    """Draw fixed widget artwork without embedded code or form actions."""
    stream = DecodedStreamObject()
    stream.set_data(
        b"q 0.95 g 0 0 160 28 re f Q\n"
        + (b"q 0 0 0 RG 2 w 5 5 m 15 18 l 25 4 l S Q\n" if checked
           else b"q 0 0 0 RG 1 w 1 1 158 26 re S Q\n")
    )
    stream[NameObject("/Type")] = NameObject("/XObject")
    stream[NameObject("/Subtype")] = NameObject("/Form")
    stream[NameObject("/FormType")] = NumberObject(1)
    stream[NameObject("/BBox")] = ArrayObject(map(NumberObject, (0, 0, 160, 28)))
    stream[NameObject("/Resources")] = DictionaryObject()
    return writer._add_object(stream)


def _document_with_field(kind):
    """Build real /AcroForm fields, page widgets and appearance streams."""
    writer = PdfWriter()
    page = writer.add_blank_page(width=300, height=200)
    names = {
        "text": ("/Tx", "Fixture text"),
        "checkbox": ("/Btn", "/Yes"),
        "choice": ("/Ch", "Option A"),
    }
    field_type, value = names[kind]
    field = DictionaryObject({
        NameObject("/FT"): NameObject(field_type),
        NameObject("/T"): TextStringObject("Fixture " + kind),
        NameObject("/V"): (NameObject(value) if kind == "checkbox"
                           else TextStringObject(value)),
    })
    if kind == "choice":
        field[NameObject("/Ff")] = NumberObject(1 << 17)  # Combo box.
        field[NameObject("/Opt")] = ArrayObject([
            TextStringObject("Option A"), TextStringObject("Option B"),
        ])
    field_ref = writer._add_object(field)
    normal = (
        DictionaryObject({
            NameObject("/Off"): _appearance(writer),
            NameObject("/Yes"): _appearance(writer, checked=True),
        }) if kind == "checkbox" else _appearance(writer)
    )
    widget = DictionaryObject({
        NameObject("/Type"): NameObject("/Annot"),
        NameObject("/Subtype"): NameObject("/Widget"),
        NameObject("/Rect"): ArrayObject(map(NumberObject, (50, 70, 210, 98))),
        NameObject("/F"): NumberObject(4),
        NameObject("/P"): page.indirect_reference,
        NameObject("/Parent"): field_ref,
        NameObject("/AP"): DictionaryObject({NameObject("/N"): normal}),
    })
    if kind == "checkbox":
        widget[NameObject("/AS")] = NameObject("/Yes")
    widget_ref = writer._add_object(widget)
    field[NameObject("/Kids")] = ArrayObject([widget_ref])
    page[NameObject("/Annots")] = ArrayObject([widget_ref])
    writer._root_object[NameObject("/AcroForm")] = writer._add_object(
        DictionaryObject({
            NameObject("/Fields"): ArrayObject([field_ref]),
            NameObject("/NeedAppearances"): BooleanObject(False),
        })
    )
    output = BytesIO()
    writer.write(output)
    return output.getvalue()


# Actual PDFs, synthesized in-memory with pinned pypdf at test time. They
# never mix with REFERENCE_PDFS or any scanner verdict simulation.
INTERACTIVE_FORM_PDFS = tuple(
    InteractiveFormPDF(
        f"acroform-{kind}", _document_with_field(kind), field_type, value
    )
    for kind, (field_type, value) in (
        ("text", ("/Tx", "Fixture text")),
        ("checkbox", ("/Btn", "/Yes")),
        ("choice", ("/Ch", "Option A")),
    )
)
