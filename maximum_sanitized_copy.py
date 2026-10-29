"""Opt-in, visual-only sanitized PDF copy offer for future Maximum (opener-0313).

A compiled macOS CoreGraphics converter is optional. Missing dependencies,
unsupported documents, truncated conversion and invalid output never offer a
copy. This module neither saves nor opens documents, and it cannot override
the installed scanner or user preferences.
"""

from dataclasses import dataclass
from decimal import Decimal
from enum import Enum
from io import BytesIO
import math
import os
from pathlib import Path
import stat
import sys

from maximum_active_content_removal import remove_active_pdf_functionality
from maximum_sanitizer_process import (
    SanitizerProcessExecutionError,
    SanitizerProcessMemoryLimitError,
    SanitizerProcessOutputLimitExceeded,
    SanitizerProcessTimedOut,
    run_limited_converter,
)
from maximum_sanitized_structure import verify_sanitized_pdf_structure

MAX_SOURCE_BYTES = 16 * 1024 * 1024
MAX_OUTPUT_BYTES = 32 * 1024 * 1024
MAX_PAGES = 16
CONVERSION_TIMEOUT_SECONDS = 45
GENERATED_CONTENT_ORIGIN = "generatedContent"
OFFER_LABEL = "Save generated sanitized PDF copy"
OFFER_EXPLANATION = (
    "This is newly generated content, not the untouched original PDF. "
    "Flattening pages into images can remove selectable text and searchability; "
    "links, forms, attachments and other interactive features are not preserved. "
    "OCR restoration is not included. "
    "Flattening can invalidate digital signatures; the generated copy "
    "must not be treated as a signed original. "
    "This is not a malware-clean verdict; scan the generated copy separately."
)


CONVERSION_CHANGE_WARNING = (
    "Warning: Converting this PDF meaningfully changes the document. "
    "The generated copy contains flattened page images rather than the original "
    "PDF content. Searchable text, forms, links, annotations, and document metadata "
    "are removed, and some visual details may render differently. "
    "Review the generated copy before relying on it."
)

@dataclass(frozen=True)
class SanitizedCopyOffer:
    """In-memory, user-initiated save option, never a permission to open."""

    pdf_bytes: bytes
    page_count: int
    label: str = OFFER_LABEL
    explanation: str = OFFER_EXPLANATION
    permits_open: bool = False
    needs_separate_scan: bool = True
    rasterized: bool = True
    # OCR is reserved for a separate future opt-in feature, not this safe-copy offer.
    ocr_restored: bool = False
    content_origin: str = GENERATED_CONTENT_ORIGIN
    warning: str = CONVERSION_CHANGE_WARNING

    def to_public_metadata(self):
        """Fixed presentation evidence; never include bytes or private paths."""
        return {
            "contentOrigin": GENERATED_CONTENT_ORIGIN,
            "isUntouchedOriginal": False,
            "label": OFFER_LABEL,
            "explanation": OFFER_EXPLANATION,
            "conversionWarning": CONVERSION_CHANGE_WARNING,
            "requiresFreshScan": True,
            "authorizesOpen": False,
            "ocrRestored": False,
        }

    def __post_init__(self):
        if (type(self.pdf_bytes) is not bytes or
                not 0 < len(self.pdf_bytes) <= MAX_OUTPUT_BYTES or
                type(self.page_count) is not int or
                not 1 <= self.page_count <= MAX_PAGES or
                self.label != OFFER_LABEL or
                self.explanation != OFFER_EXPLANATION or
                self.warning != CONVERSION_CHANGE_WARNING or
                self.permits_open is not False or
                self.needs_separate_scan is not True or
                self.rasterized is not True or
                self.ocr_restored is not False or
                type(self.content_origin) is not str or
                self.content_origin != GENERATED_CONTENT_ORIGIN):
            raise ValueError("Sanitized copies never grant scan or open approval")


class SanitizerFailureKind(str, Enum):
    """No sanitizer failure is a malware scan verdict."""

    UNSUPPORTED_INPUT = "unsupportedInput"
    UNAVAILABLE = "sanitizerUnavailable"
    CRASHED = "sanitizerCrashed"
    TIMED_OUT = "sanitizerTimedOut"
    MEMORY_LIMIT_FAILED = "sanitizerMemoryLimitFailed"
    LAUNCH_FAILED = "sanitizerLaunchFailed"
    PROCESS_FAILED = "sanitizerProcessFailed"
    INVALID_OUTPUT = "sanitizerInvalidOutput"


# Fixed, path-free user messages; never interpolate a source pathname,
# worker stdout/stderr, PDF text, signal details, or scanner signatures.
_FAILURE_MESSAGES = {
    SanitizerFailureKind.UNSUPPORTED_INPUT: (
        "This PDF cannot be converted to a sanitized copy; no copy was offered."
    ),
    SanitizerFailureKind.UNAVAILABLE: (
        "The PDF sanitizer is unavailable; no copy was offered."
    ),
    SanitizerFailureKind.CRASHED: (
        "The PDF sanitizer crashed; conversion stopped. This is not a malware detection."
    ),
    SanitizerFailureKind.TIMED_OUT: (
        "The PDF sanitizer timed out; conversion stopped. This is not a malware detection."
    ),
    SanitizerFailureKind.MEMORY_LIMIT_FAILED: (
        "The PDF sanitizer exceeded or could not verify its memory limit; conversion stopped. "
        "This is not a malware detection."
    ),
    SanitizerFailureKind.LAUNCH_FAILED: (
        "The PDF sanitizer could not start; conversion stopped. This is not a malware detection."
    ),
    SanitizerFailureKind.PROCESS_FAILED: (
        "The PDF sanitizer failed during conversion. This is not a malware detection."
    ),
    SanitizerFailureKind.INVALID_OUTPUT: (
        "The PDF sanitizer did not produce a verified copy. This is not a malware detection."
    ),
}


@dataclass(frozen=True)
class SanitizerFailureReport:
    """Sanitizer diagnostic only; never a scan result or opening permission."""

    kind: SanitizerFailureKind
    message: str
    permits_open: bool = False
    scan_verdict: str = "notAssessed"

    def __post_init__(self):
        if (type(self.kind) is not SanitizerFailureKind or
                self.message != _FAILURE_MESSAGES[self.kind] or
                self.permits_open is not False or
                self.scan_verdict != "notAssessed"):
            raise ValueError("Sanitizer failures cannot become malware or clean verdicts")

    def to_dict(self) -> dict:
        return {
            "status": "sanitizerFailure",
            "kind": self.kind.value,
            "message": self.message,
            "scanVerdict": "notAssessed",
            "permitsOpen": False,
        }


@dataclass(frozen=True)
class SanitizerAttempt:
    """Exactly one verified offer or a separately typed sanitizer failure."""

    offer: SanitizedCopyOffer | None
    failure: SanitizerFailureReport | None

    def __post_init__(self):
        if ((self.offer is None) == (self.failure is None) or
                (self.offer is not None and type(self.offer) is not SanitizedCopyOffer) or
                (self.failure is not None and type(self.failure) is not SanitizerFailureReport)):
            raise ValueError("A sanitizer attempt needs exactly one outcome")

    @property
    def permits_open(self) -> bool:
        return False


def _failed(kind: SanitizerFailureKind) -> SanitizerAttempt:
    return SanitizerAttempt(None, SanitizerFailureReport(kind, _FAILURE_MESSAGES[kind]))


class SanitizationBlockReason(str, Enum):
    """Fixed, source-independent reasons why a Maximum copy is unavailable."""

    invalidSource = "invalidSource"
    converterUnavailable = "converterUnavailable"
    encryptedSource = "encryptedSource"
    unsupportedPages = "unsupportedPages"
    unsupportedFeature = "unsupportedFeature"
    unreadableSource = "unreadableSource"
    conversionFailed = "conversionFailed"
    outputUnverified = "outputUnverified"


@dataclass(frozen=True)
class SanitizationDecision:
    """Explicit terminal Maximum copy decision, never a clean/open verdict.

    An absent offer must be a BLOCK with a fixed reason. An offer must
    carry the original immutable, separately-scannable in-memory copy.
    No PDF-controlled data is interpolated into the decision metadata.
    """

    offer: SanitizedCopyOffer | None
    blocked_reason: SanitizationBlockReason | None

    def __post_init__(self):
        ready = type(self.offer) is SanitizedCopyOffer
        blocked = type(self.blocked_reason) is SanitizationBlockReason
        if ready == blocked:
            raise ValueError("A sanitized copy must be verified or blocked")

    @property
    def action(self) -> str:
        return "offerForSeparateScan" if self.offer is not None else "block"

    @property
    def permits_open(self) -> bool:
        return False

    @property
    def allow_fallback(self) -> bool:
        return False

    @property
    def allow_clean_cache(self) -> bool:
        return False

    @property
    def preserve_quarantine(self) -> bool:
        return True

    @property
    def requires_separate_scan(self) -> bool:
        return True

    def to_dict(self) -> dict:
        return {
            "action": self.action,
            "reason": (self.blocked_reason.value if self.blocked_reason is not None
                       else None),
            "offerAvailable": self.offer is not None,
            "pageCount": self.offer.page_count if self.offer is not None else None,
            "permitsOpen": False,
            "allowFallback": False,
            "allowCleanCache": False,
            "preserveQuarantine": True,
            "requiresSeparateScan": True,
            **({"conversionWarning": CONVERSION_CHANGE_WARNING}
               if self.offer is not None else {}),
        }


def _blocked(reason: SanitizationBlockReason) -> SanitizationDecision:
    return SanitizationDecision(None, reason)


_KNOWN_PASSIVE_FILTERS = frozenset({
    "/FlateDecode", "/LZWDecode", "/ASCII85Decode", "/ASCIIHexDecode",
    "/RunLengthDecode", "/CCITTFaxDecode", "/DCTDecode", "/JPXDecode",
    "/JBIG2Decode",
})


def _unsupported_filter(obj) -> bool:
    """Inspect only stream filter *names*, never decompress source bytes."""
    value = obj.get("/Filter")
    if value is None:
        return False
    values = value if isinstance(value, (list, tuple)) else (value,)
    return (not 1 <= len(values) <= 8 or
            any(str(v.get_object()) not in _KNOWN_PASSIVE_FILTERS
                for v in values))


def _unsupported_source_features(original) -> bool:
    """Conservatively reject PDF features without reliable static raster fidelity.

    Normal document JavaScript, annotations, attachments, and forms may be
    discarded by the visual-only converter. XFA, layered content, portfolios
    and rich media cannot be claimed to have a faithful static view. Inspect
    trusted PDF *structure* only; never execute actions or open attachments.
    Unknown/malformed structures are rejected by the caller.
    """
    root = original.trailer["/Root"]
    if any(name in root for name in (
        "/NeedsRendering", "/Collection", "/OCProperties", "/Perms",
    )):
        return True
    form = root.get("/AcroForm")
    if form is not None:
        form = form.get_object()
        if "/XFA" in form or int(form.get("/SigFlags", 0)) & 0b11:
            return True
    forbidden_subtypes = {
        "/RichMedia", "/3D", "/Movie", "/Screen", "/Sound",
    }
    for page in original.pages:
        # A converter may render an incomplete page without admitting that a
        # stream filter was unsupported. Reject unknown filter names before
        # it runs; never decode unknown or potentially dangerous source data.
        contents = page.get("/Contents")
        if contents is not None:
            contents = contents.get_object()
            streams = contents if isinstance(contents, (list, tuple)) else (contents,)
            if len(streams) > 128:
                return True
            for ref in streams:
                if _unsupported_filter(ref.get_object()):
                    return True
        resources = page.get("/Resources")
        if resources is not None:
            objects = resources.get_object().get("/XObject")
            if objects is not None:
                objects = objects.get_object()
                if len(objects) > 128:
                    return True
                for ref in objects.values():
                    if _unsupported_filter(ref.get_object()):
                        return True
        annots = page.get("/Annots")
        if annots is None:
            continue
        annots = annots.get_object()
        for ref in annots:
            annotation = ref.get_object()
            if annotation.get("/Subtype") in forbidden_subtypes or (
                    "/3DD" in annotation or "/RichMediaContent" in annotation):
                return True
    return False


def _trusted_converter() -> Path | None:
    if sys.platform != "darwin":
        return None
    binary = Path(__file__).resolve().with_name("maximum-sanitized-copy")
    try:
        if binary.is_symlink() or not binary.is_file():
            return None
        attributes = binary.stat(follow_symlinks=False)
        if (not stat.S_ISREG(attributes.st_mode) or
                attributes.st_mode & (stat.S_IWGRP | stat.S_IWOTH) or
                attributes.st_uid not in (0, os.geteuid()) or
                not os.access(binary, os.X_OK)):
            return None
        return binary
    except OSError:
        return None


def _page_geometry(page):
    """Return validated, normalized page dimensions and right-angle rotation."""
    try:
        width = float(page.mediabox.width)
        height = float(page.mediabox.height)
        rotation = page.get_inherited("/Rotate")
        if rotation is None:
            rotation = 0
        if (isinstance(rotation, bool) or
                not isinstance(rotation, (int, float, Decimal))):
            return None
        numeric_rotation = float(rotation)
        if (not math.isfinite(numeric_rotation) or
                not numeric_rotation.is_integer() or int(numeric_rotation) % 90 != 0):
            return None
        rotation = int(numeric_rotation) % 360
        if (rotation not in (0, 90, 180, 270) or
                not math.isfinite(width) or not math.isfinite(height) or
                not 1 <= width <= 1440 or not 1 <= height <= 1440):
            return None
        return (width, height, rotation)
    except Exception:
        return None


def _passive_pages(
    pdf_bytes: bytes, count: int,
    expected_page_geometry: tuple[tuple[float, float, int], ...] | None = None,
) -> bool:
    """Check generated output has only new pages/images, not PDF actions.

    This is validation, not a guarantee that a PDF reader has no bugs.
    """
    try:
        from pypdf import PdfReader
        reader = PdfReader(BytesIO(pdf_bytes), strict=True)
        if (reader.is_encrypted or len(reader.pages) != count or
                (expected_page_geometry is not None and (
                    type(expected_page_geometry) is not tuple or
                    len(expected_page_geometry) != count
                ))):
            return False
        root = reader.trailer["/Root"]
        if set(root) - {"/Type", "/Pages"}:
            return False
        for index, page in enumerate(reader.pages):
            geometry = _page_geometry(page)
            if geometry is None:
                return False
            if expected_page_geometry is not None:
                expected = expected_page_geometry[index]
                if (type(expected) is not tuple or len(expected) != 3 or
                        any(type(value) not in (int, float) for value in expected[:2]) or
                        type(expected[2]) is not int or
                        abs(geometry[0] - expected[0]) > 0.01 or
                        abs(geometry[1] - expected[1]) > 0.01 or
                        geometry[2] != expected[2]):
                    return False
            if any(item in page for item in (
                "/Annots", "/AA", "/OpenAction", "/Names", "/AcroForm",
                "/EmbeddedFiles", "/RichMedia", "/Metadata",
            )):
                return False
            resources = page.get("/Resources")
            if not resources:
                return False
            resources = resources.get_object()
            if set(resources) - {"/XObject", "/ProcSet"}:
                return False
            images = resources.get("/XObject")
            if not images:
                return False
            images = images.get_object()
            if not images:
                return False
            # Only the fixed image drawing instruction emitted by our fresh
            # pixel-plane writer is permitted. OCR text operators, invisible
            # overlays, appended content streams and resource substitutions
            # must never pass the final output or generated-rescan gate.
            if set(images) != {"/Im0"} or any(
                    obj.get_object().get("/Subtype") != "/Image"
                    for obj in images.values()):
                return False
            from pypdf.generic import StreamObject
            content = page.get("/Contents")
            if content is None:
                return False
            content = content.get_object()
            if not isinstance(content, StreamObject) or "/Filter" in content:
                return False
            width, height, _ = geometry
            expected_drawing = (
                f"q {width:.4f} 0 0 {height:.4f} 0 0 cm /Im0 Do Q\n"
            ).encode("ascii")
            if content.get_data() != expected_drawing:
                return False
        return True
    except Exception:
        return False


def attempt_sanitized_pdf_copy(source_bytes: bytes) -> SanitizerAttempt:
    """Report converter crashes separately, never infer malware from a crash.

    A verified offer is distinct from sanitization failures; neither
    authorizes opening or changes the installed ClamAV scan result. Only
    the scanner may assign a malware-detected status. All diagnostics use
    fixed messages without paths, PDF text or worker output.
    """
    if (type(source_bytes) is not bytes or
            not 0 < len(source_bytes) <= MAX_SOURCE_BYTES or
            not source_bytes.startswith(b"%PDF-")):
        return _failed(SanitizerFailureKind.UNSUPPORTED_INPUT)
    try:
        converter = _trusted_converter()
    except Exception:
        return _failed(SanitizerFailureKind.UNAVAILABLE)
    if converter is None:
        return _failed(SanitizerFailureKind.UNAVAILABLE)
    try:
        from pypdf import PdfReader
        original = PdfReader(BytesIO(source_bytes), strict=True)
        if original.is_encrypted or not 1 <= len(original.pages) <= MAX_PAGES:
            return _failed(SanitizerFailureKind.UNSUPPORTED_INPUT)
        if _unsupported_source_features(original):
            # Unsupported dynamic features and unknown filters must never
            # reach a converter that could silently drop their content.
            return _failed(SanitizerFailureKind.UNSUPPORTED_INPUT)
        page_geometry = tuple(_page_geometry(page) for page in original.pages)
        if not page_geometry or any(item is None for item in page_geometry):
            return _failed(SanitizerFailureKind.UNSUPPORTED_INPUT)
        count = len(page_geometry)
    except Exception:
        return _failed(SanitizerFailureKind.UNSUPPORTED_INPUT)

    try:
        converted = run_limited_converter(
            (str(converter),),
            source_bytes,
            timeout_seconds=CONVERSION_TIMEOUT_SECONDS,
            max_output_bytes=MAX_OUTPUT_BYTES,
            environment={"PATH": "/usr/bin:/bin", "HOME": "/var/empty",
                         "LANG": "C", "PYTHONDONTWRITEBYTECODE": "1"},
        )
    except SanitizerProcessMemoryLimitError:
        return _failed(SanitizerFailureKind.MEMORY_LIMIT_FAILED)
    except SanitizerProcessTimedOut:
        return _failed(SanitizerFailureKind.TIMED_OUT)
    except SanitizerProcessOutputLimitExceeded:
        return _failed(SanitizerFailureKind.INVALID_OUTPUT)
    except (OSError, SanitizerProcessExecutionError):
        return _failed(SanitizerFailureKind.LAUNCH_FAILED)
    except Exception:
        return _failed(SanitizerFailureKind.LAUNCH_FAILED)

    if type(converted.returncode) is not int:
        return _failed(SanitizerFailureKind.INVALID_OUTPUT)
    if converted.returncode < 0:
        # POSIX negative exit status means the child died from a signal.
        # Never present this as a ClamAV malware detection.
        return _failed(SanitizerFailureKind.CRASHED)
    if converted.returncode != 0:
        return _failed(SanitizerFailureKind.PROCESS_FAILED)
    if (type(converted.stdout) is not bytes or
            not 0 < len(converted.stdout) <= MAX_OUTPUT_BYTES or
            converted.stdout == source_bytes):
        return _failed(SanitizerFailureKind.INVALID_OUTPUT)

    try:
        # The opt-in converter's output is never itself offered. Keep only
        # decoded raster pixels through a new PDF construction.
        cleaned = remove_active_pdf_functionality(
            converted.stdout, count, page_geometry,
        )
        if (type(cleaned) is not bytes or
                not 0 < len(cleaned) <= MAX_OUTPUT_BYTES or
                cleaned == source_bytes or
                not _passive_pages(cleaned, count, page_geometry)):
            # Never offer the original, a non-PDF or an incomplete rebuild.
            return _failed(SanitizerFailureKind.INVALID_OUTPUT)
        # Preserve opener-0319's independent verification of final output.
        structure = verify_sanitized_pdf_structure(cleaned, count)
        if structure.page_count != count:
            return _failed(SanitizerFailureKind.INVALID_OUTPUT)
        return SanitizerAttempt(SanitizedCopyOffer(cleaned, count), None)
    except Exception:
        return _failed(SanitizerFailureKind.INVALID_OUTPUT)


def assess_sanitized_pdf_copy(source_bytes: bytes) -> SanitizationDecision:
    """Classify unsupported sanitization without changing crash-reporting.

    Only verified offers from the existing sanitizer attempt may be
    published. Other conditions are fixed blocked codes; no original
    document, unverified conversion, or malware/clean verdict is exposed.
    """
    if (type(source_bytes) is not bytes or
            not 0 < len(source_bytes) <= MAX_SOURCE_BYTES or
            not source_bytes.startswith(b"%PDF-")):
        return _blocked(SanitizationBlockReason.invalidSource)
    try:
        converter = _trusted_converter()
    except Exception:
        return _blocked(SanitizationBlockReason.converterUnavailable)
    if converter is None:
        return _blocked(SanitizationBlockReason.converterUnavailable)
    try:
        from pypdf import PdfReader
        original = PdfReader(BytesIO(source_bytes), strict=True)
        if original.is_encrypted:
            return _blocked(SanitizationBlockReason.encryptedSource)
        if not 1 <= len(original.pages) <= MAX_PAGES:
            return _blocked(SanitizationBlockReason.unsupportedPages)
        if _unsupported_source_features(original):
            return _blocked(SanitizationBlockReason.unsupportedFeature)
    except Exception:
        return _blocked(SanitizationBlockReason.unreadableSource)

    attempt = attempt_sanitized_pdf_copy(source_bytes)
    if attempt.offer is not None:
        return SanitizationDecision(attempt.offer, None)
    # Keep the separately typed sanitizer-crash result on
    # attempt_sanitized_pdf_copy(); this policy must not conflate it with
    # either a clean scan or malware detection.
    if attempt.failure.kind is SanitizerFailureKind.UNAVAILABLE:
        return _blocked(SanitizationBlockReason.converterUnavailable)
    if attempt.failure.kind is SanitizerFailureKind.UNSUPPORTED_INPUT:
        return _blocked(SanitizationBlockReason.unreadableSource)
    if attempt.failure.kind is SanitizerFailureKind.INVALID_OUTPUT:
        return _blocked(SanitizationBlockReason.outputUnverified)
    return _blocked(SanitizationBlockReason.conversionFailed)


def offer_sanitized_pdf_copy(source_bytes: bytes) -> SanitizedCopyOffer | None:
    """Compatibility API: an unsuccessful conversion still offers nothing.

    Use attempt_sanitized_pdf_copy() when callers need to show a specific
    sanitizer failure without conflating it with malware detections.
    """
    return attempt_sanitized_pdf_copy(source_bytes).offer
