"""Inert, deterministic JavaScript-action PDFs for security corpus tests.

These are in-memory PDF *documents*, not executable JavaScript test programs.
Do not open the samples in a script-capable viewer. They are never inputs to
ClamAV verdict simulation or an allow-to-open decision.
"""

from dataclasses import dataclass
from io import BytesIO

from pypdf import PdfWriter
from pypdf.generic import (
    ArrayObject, DecodedStreamObject, DictionaryObject, NameObject,
    TextStringObject,
)


@dataclass(frozen=True)
class JavaScriptActionPDF:
    identifier: str
    content: bytes
    expected_trigger: str
    expected_payload_type: str
    expected_hints: tuple[str, ...]


def _document_with_action(location: str, script: str, stream: bool = False) -> bytes:
    writer = PdfWriter()
    writer.add_blank_page(width=612, height=792)
    if stream:
        payload = DecodedStreamObject()
        payload.set_data(script.encode("utf-8"))
        value = writer._add_object(payload)
    else:
        value = TextStringObject(script)
    action = writer._add_object(DictionaryObject({
        NameObject("/S"): NameObject("/JavaScript"),
        NameObject("/JS"): value,
    }))

    if location == "open":
        writer._root_object[NameObject("/OpenAction")] = action
    elif location == "page":
        writer.pages[0][NameObject("/AA")] = DictionaryObject({
            NameObject("/O"): action,
        })
    elif location == "names":
        writer._root_object[NameObject("/Names")] = DictionaryObject({
            NameObject("/JavaScript"): DictionaryObject({
                NameObject("/Names"): ArrayObject([
                    TextStringObject("InertExample"), action,
                ]),
            }),
        })
    else:
        raise ValueError("Unknown PDF JavaScript action fixture location")

    output = BytesIO()
    writer.write(output)
    return output.getvalue()


# Deliberately separate from REFERENCE_PDFS, whose members must remain free of
# active content for existing clean-baseline regressions. .invalid is reserved;
# it must never be resolved, fetched, launched or submitted to by tests.
JAVASCRIPT_ACTION_PDFS = (
    JavaScriptActionPDF(
        "javascript-document-open",
        _document_with_action("open", "app.alert('Inert PDF fixture'); eval('0');"),
        "document_open", "text", ("dynamic_execution",),
    ),
    JavaScriptActionPDF(
        "javascript-page-additional",
        _document_with_action("page", "app.launchURL('https://example.invalid');"),
        "page_additional", "text", ("network",),
    ),
    JavaScriptActionPDF(
        "javascript-document-name-tree-stream",
        _document_with_action("names", "this.exportDataObject('InertFixture');", stream=True),
        "document_javascript", "stream", ("file_access",),
    ),
)
