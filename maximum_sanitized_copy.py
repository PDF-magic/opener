"""Opt-in, visual-only sanitized PDF copy offer for future Maximum (opener-0313).

A compiled macOS CoreGraphics converter is optional. Missing dependencies,
unsupported documents, truncated conversion and invalid output never offer a
copy. This module neither saves nor opens documents, and it cannot override
the installed scanner or user preferences.
"""

from dataclasses import dataclass
from io import BytesIO
import os
from pathlib import Path
import stat
import subprocess
import sys

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


def offer_sanitized_pdf_copy(source_bytes: bytes) -> SanitizedCopyOffer | None:
    """Return an offer only when a complete *new* rasterized copy was verified.

    Conversion is on-demand. No file is written, displayed or launched here:
    a future Maximum UI must ask the user to save the copy, and route that
    new document through the normal mandatory scan before any opening.
    Unsupported or failed conversions return None without disclosing PDF data.
    """
    if (type(source_bytes) is not bytes or
            not 0 < len(source_bytes) <= MAX_SOURCE_BYTES or
            not source_bytes.startswith(b"%PDF-")):
        return None
    converter = _trusted_converter()
    if converter is None:
        return None
    try:
        from pypdf import PdfReader
        original = PdfReader(BytesIO(source_bytes), strict=True)
        if original.is_encrypted or not 1 <= len(original.pages) <= MAX_PAGES:
            return None
        count = len(original.pages)
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
        if (converted.returncode != 0 or
                type(converted.stdout) is not bytes or
                not 0 < len(converted.stdout) <= MAX_OUTPUT_BYTES or
                converted.stdout == source_bytes or
                not _passive_pages(converted.stdout, count)):
            return None
        return SanitizedCopyOffer(converted.stdout, count)
    except Exception:
        return None
