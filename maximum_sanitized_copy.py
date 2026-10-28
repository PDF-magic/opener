"""Opt-in, visual-only sanitized PDF copy offer for future Maximum (opener-0313).

A compiled macOS CoreGraphics converter is optional. Missing dependencies,
unsupported documents, truncated conversion and invalid output never offer a
copy. This module neither saves nor opens documents, and it cannot override
the installed scanner or user preferences.
"""

from dataclasses import dataclass
from enum import Enum
from io import BytesIO
import os
from pathlib import Path
import stat
import subprocess
import sys

from maximum_active_content_removal import remove_active_pdf_functionality

MAX_SOURCE_BYTES = 16 * 1024 * 1024
MAX_OUTPUT_BYTES = 32 * 1024 * 1024
MAX_PAGES = 16
CONVERSION_TIMEOUT_SECONDS = 45
OFFER_LABEL = "Save rasterized PDF copy"
OFFER_EXPLANATION = (
    "Pages are flattened into images; searchable text, links, forms, "
    "attachments and other interactive features are not preserved. "
    "This is not a malware-clean verdict; scan the generated copy separately."
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

    def __post_init__(self):
        if (type(self.pdf_bytes) is not bytes or
                not 0 < len(self.pdf_bytes) <= MAX_OUTPUT_BYTES or
                type(self.page_count) is not int or
                not 1 <= self.page_count <= MAX_PAGES or
                self.label != OFFER_LABEL or
                self.explanation != OFFER_EXPLANATION or
                self.permits_open is not False or
                self.needs_separate_scan is not True or
                self.rasterized is not True):
            raise ValueError("Sanitized copies never grant scan or open approval")


class SanitizerFailureKind(str, Enum):
    """No sanitizer failure is a malware scan verdict."""

    UNSUPPORTED_INPUT = "unsupportedInput"
    UNAVAILABLE = "sanitizerUnavailable"
    CRASHED = "sanitizerCrashed"
    TIMED_OUT = "sanitizerTimedOut"
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


def _passive_pages(pdf_bytes: bytes, count: int) -> bool:
    """Check generated output has only new pages/images, not PDF actions.

    This is validation, not a guarantee that a PDF reader has no bugs.
    """
    try:
        from pypdf import PdfReader
        reader = PdfReader(BytesIO(pdf_bytes), strict=True)
        if reader.is_encrypted or len(reader.pages) != count:
            return False
        root = reader.trailer["/Root"]
        if set(root) - {"/Type", "/Pages"}:
            return False
        for page in reader.pages:
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
            if any(obj.get_object().get("/Subtype") != "/Image"
                   for obj in images.values()):
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
    converter = _trusted_converter()
    if converter is None:
        return _failed(SanitizerFailureKind.UNAVAILABLE)
    try:
        from pypdf import PdfReader
        original = PdfReader(BytesIO(source_bytes), strict=True)
        if original.is_encrypted or not 1 <= len(original.pages) <= MAX_PAGES:
            return _failed(SanitizerFailureKind.UNSUPPORTED_INPUT)
        count = len(original.pages)
    except Exception:
        return _failed(SanitizerFailureKind.UNSUPPORTED_INPUT)

    try:
        converted = subprocess.run(
            [str(converter)],
            input=source_bytes,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            timeout=CONVERSION_TIMEOUT_SECONDS,
            close_fds=True,
            start_new_session=True,
            check=False,
            cwd="/",
            env={"PATH": "/usr/bin:/bin", "HOME": "/var/empty",
                 "LANG": "C", "PYTHONDONTWRITEBYTECODE": "1"},
        )
    except subprocess.TimeoutExpired:
        return _failed(SanitizerFailureKind.TIMED_OUT)
    except (OSError, subprocess.SubprocessError):
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
        cleaned = remove_active_pdf_functionality(converted.stdout, count)
        if cleaned is None or not _passive_pages(cleaned, count):
            return _failed(SanitizerFailureKind.INVALID_OUTPUT)
        return SanitizerAttempt(SanitizedCopyOffer(cleaned, count), None)
    except Exception:
        return _failed(SanitizerFailureKind.INVALID_OUTPUT)


def offer_sanitized_pdf_copy(source_bytes: bytes) -> SanitizedCopyOffer | None:
    """Compatibility API: an unsuccessful conversion still offers nothing.

    Use attempt_sanitized_pdf_copy() when callers need to show a specific
    sanitizer failure without conflating it with malware detections.
    """
    return attempt_sanitized_pdf_copy(source_bytes).offer
