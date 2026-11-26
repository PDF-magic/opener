"""Deterministic PDFs with nonresolving external launch actions for corpus tests.

Never open or render these documents in an action-capable PDF viewer. The
fixtures are parsed only; they do not authorize launches or scanner bypasses.
"""

from dataclasses import dataclass
from io import BytesIO

from pypdf import PdfWriter
from pypdf.generic import ArrayObject, DictionaryObject, NameObject, NumberObject, TextStringObject


@dataclass(frozen=True)
class ExternalLaunchPDF:
    identifier: str
    content: bytes
    expected_trigger: str | None
    expected_actions: int
    expected_targets: tuple[str, ...]


def _launch_action(target: str) -> DictionaryObject:
    action = DictionaryObject({NameObject("/S"): NameObject("/Launch")})
    if target == "file":
        action[NameObject("/F")] = TextStringObject("nonexistent-launch-fixture.invalid")
    elif target == "filespec":
        action[NameObject("/F")] = DictionaryObject({
            NameObject("/Type"): NameObject("/Filespec"),
            NameObject("/F"): TextStringObject("nonexistent-launch-fixture.invalid"),
            NameObject("/UF"): TextStringObject("nonexistent-launch-fixture.invalid"),
        })
    elif target == "windows":
        action[NameObject("/Win")] = DictionaryObject({
            NameObject("/F"): TextStringObject("nonexistent-launch-fixture.invalid"),
            NameObject("/P"): TextStringObject("NO_EXECUTION"),
        })
    else:
        raise ValueError("unknown inert launch target")
    return action


def _document_with_launch(placement: str, target: str, chained: bool = False) -> bytes:
    writer = PdfWriter()
    page = writer.add_blank_page(width=612, height=792)
    action = _launch_action(target)
    if chained:
        action[NameObject("/Next")] = writer._add_object(_launch_action("windows"))
    action_ref = writer._add_object(action)
    if placement == "open":
        writer._root_object[NameObject("/OpenAction")] = action_ref
    elif placement == "page":
        page[NameObject("/AA")] = DictionaryObject({NameObject("/O"): action_ref})
    elif placement == "annotation":
        annotation = DictionaryObject({
            NameObject("/Type"): NameObject("/Annot"),
            NameObject("/Subtype"): NameObject("/Link"),
            NameObject("/Rect"): ArrayObject([NumberObject(0)] * 4),
            NameObject("/A"): action_ref,
        })
        page[NameObject("/Annots")] = ArrayObject([writer._add_object(annotation)])
    else:
        raise ValueError("unknown launch action placement")
    buffer = BytesIO()
    writer.write(buffer)
    return buffer.getvalue()


# Active-content cases must never enter REFERENCE_PDFS, the six clean
# baseline samples. Targets are syntactically valid but never resolve locally.
EXTERNAL_LAUNCH_PDFS = (
    ExternalLaunchPDF(
        "launch-document-open-file", _document_with_launch("open", "file"),
        "document_open", 1, ("file",),
    ),
    ExternalLaunchPDF(
        "launch-page-additional-filespec", _document_with_launch("page", "filespec"),
        "page_additional", 1, ("file",),
    ),
    ExternalLaunchPDF(
        "launch-click-only-windows", _document_with_launch("annotation", "windows"),
        None, 1, ("windows_command",),
    ),
    ExternalLaunchPDF(
        "launch-chained-document-open", _document_with_launch("open", "file", chained=True),
        "document_open", 2, ("file", "windows_command"),
    ),
)
