"""Read JavaScript action payloads as inert evidence for planned Enhanced checks.

Reuses the automatic-action inspector's bounded graph traversal and strict PDF
parser. Scripts are never executed, returned, logged, written or submitted to
a JavaScript runtime. This is not a malware verdict or an opening authorization.
"""

from dataclasses import dataclass
import re
import zlib

from pdf_automatic_actions import (
    PDFAutomaticActionError, inspect_pdf_automatic_actions,
)


MAX_JAVASCRIPT_ACTIONS = 128
MAX_SCRIPT_BYTES = 64 * 1024
MAX_TOTAL_SCRIPT_BYTES = 256 * 1024
_ERROR = "PDF JavaScript actions could not be fully inspected; opening was stopped."
_DEPENDENCY = "PDF JavaScript inspection is unavailable; opening was stopped."

# Hints from literal API names only; obfuscation, comments and strings can
# cause false negatives/positives. Never treat missing hints as "safe".
_API_HINTS = {
    "network": re.compile(r"\b(?:launchURL|getURL|submitForm)\s*\(", re.I),
    "file_access": re.compile(
        r"\b(?:exportDataObject|importDataObject|saveAs|openDoc|getDataObjectContents)\s*\(",
        re.I,
    ),
    "dynamic_execution": re.compile(r"\b(?:eval|Function)\s*\(", re.I),
}


class PDFJavaScriptInspectionError(RuntimeError):
    """Fixed, path-free fail-closed result for uninspectable script actions."""


@dataclass(frozen=True)
class PDFJavaScriptInspection:
    """Non-executable metadata; never a clean or allow-to-open verdict."""

    action_count: int
    total_script_bytes: int
    trigger_types: tuple[str, ...]
    payload_types: tuple[str, ...]
    api_reference_hints: tuple[str, ...]

    @property
    def permits_open(self) -> bool:
        return False

    @property
    def contains_javascript(self) -> bool:
        return self.action_count > 0


def _decode_script(script, text_type, bytes_type, stream_type, name_type):
    """Decode bounded PDF script text without evaluating any expression."""
    if isinstance(script, text_type):
        data = str(script).encode("utf-8")
        payload_type = "text"
    elif isinstance(script, bytes_type):
        data = bytes(script)
        payload_type = "bytes"
    elif isinstance(script, stream_type):
        # Reject arbitrary chains, predictors, and unrecognized stream codecs.
        # Do not call pypdf's unbounded get_data() on untrusted compressed bytes.
        raw = getattr(script, "_data", None)
        if type(raw) is not bytes or len(raw) > MAX_SCRIPT_BYTES:
            raise PDFJavaScriptInspectionError(_ERROR)
        if "/DecodeParms" in script:
            raise PDFJavaScriptInspectionError(_ERROR)
        codec = script.get("/Filter")
        if codec is None:
            data = raw
        elif isinstance(codec, name_type) and str(codec) in ("/FlateDecode", "/Fl"):
            try:
                decoder = zlib.decompressobj()
                data = decoder.decompress(raw, MAX_SCRIPT_BYTES + 1)
                if (not decoder.eof or decoder.unused_data or decoder.unconsumed_tail
                        or len(data) > MAX_SCRIPT_BYTES):
                    raise PDFJavaScriptInspectionError(_ERROR)
                data += decoder.flush(MAX_SCRIPT_BYTES + 1 - len(data))
            except zlib.error:
                raise PDFJavaScriptInspectionError(_ERROR) from None
        else:
            raise PDFJavaScriptInspectionError(_ERROR)
        payload_type = "stream"
    else:
        raise PDFJavaScriptInspectionError(_ERROR)

    if not data or len(data) > MAX_SCRIPT_BYTES:
        raise PDFJavaScriptInspectionError(_ERROR)
    try:
        if data.startswith((b"\xfe\xff", b"\xff\xfe")):
            text = data.decode("utf-16")
        else:
            text = data.decode("utf-8-sig")
    except UnicodeError:
        raise PDFJavaScriptInspectionError(_ERROR) from None
    if "\x00" in text:
        raise PDFJavaScriptInspectionError(_ERROR)
    return text, len(data), payload_type


def inspect_pdf_javascript_actions(contents: bytes) -> PDFJavaScriptInspection:
    """Inspect scripts reachable through PDF action hooks, never run them.

    Validates the same open/additional/page/annotation/field/JavaScript-name-
    tree actions as the separately implemented opener-0286 inspector, including
    indirect /Next action chains. Encoded JavaScript streams are decoded only
    through a bounded, single Flate stream; other filters fail closed.
    """
    try:
        from pypdf.generic import (
            ByteStringObject, NameObject, StreamObject, TextStringObject,
        )
    except (ImportError, OSError):
        raise PDFJavaScriptInspectionError(_DEPENDENCY) from None

    count = 0
    total = 0
    triggers = set()
    payload_types = set()
    hints = set()

    def inspect(script, trigger):
        nonlocal count, total
        count += 1
        if count > MAX_JAVASCRIPT_ACTIONS:
            raise PDFJavaScriptInspectionError(_ERROR)
        text, length, kind = _decode_script(
            script, TextStringObject, ByteStringObject, StreamObject, NameObject
        )
        total += length
        if total > MAX_TOTAL_SCRIPT_BYTES:
            raise PDFJavaScriptInspectionError(_ERROR)
        triggers.add(trigger)
        payload_types.add(kind)
        for label, pattern in _API_HINTS.items():
            if pattern.search(text):
                hints.add(label)

    try:
        inspect_pdf_automatic_actions(contents, _javascript_inspector=inspect)
    except PDFAutomaticActionError:
        raise PDFJavaScriptInspectionError(_ERROR) from None
    except PDFJavaScriptInspectionError:
        raise PDFJavaScriptInspectionError(_ERROR) from None
    return PDFJavaScriptInspection(
        action_count=count, total_script_bytes=total,
        trigger_types=tuple(sorted(triggers)),
        payload_types=tuple(sorted(payload_types)),
        api_reference_hints=tuple(sorted(hints)),
    )
