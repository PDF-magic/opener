"""Render bounded PDF pages in a separate Maximum-only process.

This evidence API cannot authorize opening, change scanner policy, or select
Maximum protection. The PDF never becomes a worker pathname (opener-0314).
"""

from dataclasses import dataclass
import json
from pathlib import Path
import struct
import subprocess
import sys

MAX_PDF_BYTES = 8 * 1024 * 1024
MAX_DOCUMENT_PAGES = 512
MAX_REQUEST_PAGES = 4
MAX_RENDER_SIDE = 1024
MAX_RENDER_PIXELS = MAX_RENDER_SIDE * MAX_RENDER_SIDE
MAX_PNG_BYTES = 4 * 1024 * 1024
MAX_METADATA_BYTES = 256
WORKER_WALL_SECONDS = 30
MAGIC = b"MAXPNG01"
_HEADER = struct.Struct(">8sII")
PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"
BLOCK_MESSAGE = "Isolated PDF rendering could not complete; opening was stopped."


class MaximumPDFRenderError(RuntimeError):
    """Fixed, path-free render failure, never a positive scan verdict."""


@dataclass(frozen=True)
class RenderedPDFPage:
    page_index: int
    page_count: int
    width: int
    height: int
    worker_pid: int
    png_bytes: bytes
    permits_open: bool = False

    def __post_init__(self):
        if (type(self.page_index) is not int or not 0 <= self.page_index < MAX_DOCUMENT_PAGES or
                type(self.page_count) is not int or not 1 <= self.page_count <= MAX_DOCUMENT_PAGES or
                self.page_index >= self.page_count or
                type(self.width) is not int or type(self.height) is not int or
                not 1 <= self.width <= MAX_RENDER_SIDE or
                not 1 <= self.height <= MAX_RENDER_SIDE or
                self.width * self.height > MAX_RENDER_PIXELS or
                type(self.worker_pid) is not int or self.worker_pid <= 0 or
                type(self.png_bytes) is not bytes or
                not 33 <= len(self.png_bytes) <= MAX_PNG_BYTES or
                self.png_bytes[:8] != PNG_SIGNATURE or
                self.png_bytes[12:16] != b"IHDR" or
                self.png_bytes[16:24] != struct.pack(">II", self.width, self.height) or
                self.permits_open is not False):
            raise ValueError("Untrusted or oversized isolated page rendering")

    def to_metadata(self) -> dict:
        """Only detached fixed numeric metadata, not PDF contents or paths."""
        return {
            "pageIndex": self.page_index,
            "pageCount": self.page_count,
            "width": self.width,
            "height": self.height,
            "workerPid": self.worker_pid,
            "pngBytes": len(self.png_bytes),
            "permitsOpen": False,
        }


def _unique_pairs(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("Duplicate renderer protocol key")
        result[key] = value
    return result


def _decode_response(stdout: bytes, expected_index: int) -> RenderedPDFPage:
    if (type(stdout) is not bytes or
            not _HEADER.size + 1 <= len(stdout) <=
            _HEADER.size + MAX_METADATA_BYTES + MAX_PNG_BYTES):
        raise ValueError("Invalid renderer response length")
    magic, meta_len, png_len = _HEADER.unpack_from(stdout)
    if (magic != MAGIC or not 1 <= meta_len <= MAX_METADATA_BYTES or
            not 33 <= png_len <= MAX_PNG_BYTES or
            len(stdout) != _HEADER.size + meta_len + png_len):
        raise ValueError("Invalid renderer response frame")
    meta = json.loads(
        stdout[_HEADER.size:_HEADER.size + meta_len], object_pairs_hook=_unique_pairs
    )
    if (type(meta) is not dict or
            set(meta) != {"version", "pageIndex", "pageCount", "width",
                          "height", "workerPid", "permitsOpen"} or
            type(meta["version"]) is not int or meta["version"] != 1 or
            type(meta["pageIndex"]) is not int or meta["pageIndex"] != expected_index or
            any(type(meta[k]) is not int for k in
                ("pageCount", "width", "height", "workerPid")) or
            meta["permitsOpen"] is not False):
        raise ValueError("Untrusted renderer metadata")
    return RenderedPDFPage(
        page_index=meta["pageIndex"],
        page_count=meta["pageCount"],
        width=meta["width"],
        height=meta["height"],
        worker_pid=meta["workerPid"],
        png_bytes=stdout[_HEADER.size + meta_len:],
    )


def render_isolated_pdf_page(pdf_bytes: bytes, page_index: int) -> RenderedPDFPage:
    """Render one requested page inside an isolated limited Python worker.

    The input PDF is supplied as raw stdin bytes; no document paths or mutable
    settings are forwarded. Caller must perform the existing ClamAV,
    verified-handoff and policy checks independently: this is NOT an admission
    decision, and an image is never a claim that a PDF is safe.
    """
    if (type(pdf_bytes) is not bytes or
            not 0 < len(pdf_bytes) <= MAX_PDF_BYTES or
            type(page_index) is not int or
            not 0 <= page_index < MAX_DOCUMENT_PAGES):
        raise MaximumPDFRenderError(BLOCK_MESSAGE)

    worker = Path(__file__).resolve().with_name("maximum_render_worker.py")
    command = (sys.executable, "-I", "-B", str(worker), str(page_index))
    try:
        complete = subprocess.run(
            command, input=pdf_bytes,
            stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
            timeout=WORKER_WALL_SECONDS, check=False, close_fds=True,
            start_new_session=True, cwd="/",
            env={
                "PATH": "/usr/bin:/bin",
                "HOME": "/nonexistent",
                "LANG": "C",
                "PYTHONDONTWRITEBYTECODE": "1",
                "PYTHONNOUSERSITE": "1",
            },
        )
        if complete.returncode != 0:
            raise MaximumPDFRenderError(BLOCK_MESSAGE)
        return _decode_response(complete.stdout, page_index)
    except Exception:
        # Never expose a PDF filename, metadata, parser exception, or image
        # bytes through diagnostics. Fail closed for all worker errors.
        raise MaximumPDFRenderError(BLOCK_MESSAGE) from None


def render_isolated_pdf_pages(
    pdf_bytes: bytes, page_indices: tuple[int, ...],
) -> tuple[RenderedPDFPage, ...]:
    """Render at most four distinct pages, one bounded child per page."""
    if (type(pdf_bytes) is not bytes or
            not 0 < len(pdf_bytes) <= MAX_PDF_BYTES or
            type(page_indices) is not tuple or
            not 1 <= len(page_indices) <= MAX_REQUEST_PAGES or
            any(type(i) is not int or not 0 <= i < MAX_DOCUMENT_PAGES
                for i in page_indices) or
            len(set(page_indices)) != len(page_indices)):
        raise MaximumPDFRenderError(BLOCK_MESSAGE)
    return tuple(render_isolated_pdf_page(pdf_bytes, i) for i in page_indices)
