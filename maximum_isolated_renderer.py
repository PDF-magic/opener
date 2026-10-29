"""Render bounded PDF pages in a separate Maximum-only process.

This evidence API cannot authorize opening, change scanner policy, or select
Maximum protection. The PDF never becomes a worker pathname (opener-0314).
"""

from dataclasses import dataclass
import json
import os
from pathlib import Path
import stat
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
SANDBOX_EXEC = "/usr/bin/sandbox-exec"
RENDERER_SANDBOX_PROFILE = """(version 1)
(deny default)
(allow process-exec (literal (param "PYTHON")))
(allow sysctl-read)
(allow file-read-metadata (subpath "/"))
(allow file-read*
    (literal (param "PYTHON"))
    (literal (param "WORKER"))
    (subpath (param "WORKER_DIR"))
    (subpath (param "PYTHON_PREFIX"))
    (subpath (param "PYTHON_BASE_PREFIX"))
    (subpath "/System")
    (subpath "/usr/bin")
    (subpath "/usr/lib")
    (subpath "/usr/share")
    (subpath "/bin")
    (subpath "/sbin")
    (subpath "/Library/Developer/CommandLineTools")
    (subpath "/Library/Frameworks")
    (literal "/dev/null")
    (literal "/dev/urandom"))
"""
MAX_RENDER_ARGUMENTS = 8
MAX_RENDER_ARGUMENT_LENGTH = 4096


class MaximumPDFRenderError(RuntimeError):
    """Fixed, path-free render failure, never a positive scan verdict."""



def _trusted_regular_file(path: str, *, executable: bool = False) -> bool:
    """Accept only a canonical, non-writable trusted file for the child."""
    if (type(path) is not str or not path.startswith("/") or "\x00" in path or
            os.path.normpath(path) != path or os.path.realpath(path) != path):
        return False
    try:
        info = os.stat(path, follow_symlinks=False)
        return (
            stat.S_ISREG(info.st_mode) and
            not info.st_mode & (stat.S_IWGRP | stat.S_IWOTH) and
            info.st_uid in (0, os.geteuid()) and
            (not executable or os.access(path, os.X_OK))
        )
    except OSError:
        return False


def _trusted_directory(path: str, *, runtime: bool = False) -> bool:
    """Reject symlinks, writable paths and overly broad runtime roots."""
    minimum_components = 4 if runtime else 3
    if (type(path) is not str or not path.startswith("/") or "\x00" in path or
            os.path.normpath(path) != path or os.path.realpath(path) != path or
            len(Path(path).parts) < minimum_components):
        return False
    try:
        info = os.stat(path, follow_symlinks=False)
        return (
            stat.S_ISDIR(info.st_mode) and
            not info.st_mode & (stat.S_IWGRP | stat.S_IWOTH) and
            info.st_uid in (0, os.geteuid())
        )
    except OSError:
        return False


def _renderer_sandbox_context(worker_path: Path) -> dict[str, str]:
    """Resolve and validate the only paths the renderer process may read."""
    if sys.platform != "darwin":
        raise MaximumPDFRenderError(BLOCK_MESSAGE)
    try:
        python = str(Path(sys.executable).resolve(strict=True))
        worker = str(Path(worker_path).resolve(strict=True))
        source_root = str(Path(__file__).resolve(strict=True).parent)
        prefix = str(Path(sys.prefix).resolve(strict=True))
        base_prefix = str(Path(sys.base_prefix).resolve(strict=True))
    except (OSError, RuntimeError, TypeError):
        raise MaximumPDFRenderError(BLOCK_MESSAGE) from None

    if (Path(worker).parent != Path(source_root) or
            not _trusted_regular_file(SANDBOX_EXEC, executable=True) or
            not _trusted_regular_file(python, executable=True) or
            not _trusted_regular_file(worker) or
            not _trusted_directory(source_root) or
            not _trusted_directory(prefix, runtime=True) or
            not _trusted_directory(base_prefix, runtime=True)):
        raise MaximumPDFRenderError(BLOCK_MESSAGE)
    return {
        "python": python,
        "worker": worker,
        "worker_dir": source_root,
        "python_prefix": prefix,
        "python_base_prefix": base_prefix,
    }


def _run_confined_worker(
    worker_path: Path, arguments: tuple[str, ...], input_bytes: bytes,
) -> subprocess.CompletedProcess:
    """Run one trusted renderer helper with macOS filesystem confinement."""
    if (type(arguments) is not tuple or
            not 1 <= len(arguments) <= MAX_RENDER_ARGUMENTS or
            any(type(arg) is not str or not arg or "\x00" in arg or
                len(arg) > MAX_RENDER_ARGUMENT_LENGTH for arg in arguments) or
            type(input_bytes) is not bytes or
            not 0 < len(input_bytes) <= MAX_PDF_BYTES):
        raise MaximumPDFRenderError(BLOCK_MESSAGE)

    context = _renderer_sandbox_context(worker_path)
    command = [SANDBOX_EXEC, "-p", RENDERER_SANDBOX_PROFILE]
    for name, key in (
        ("PYTHON", "python"),
        ("WORKER", "worker"),
        ("WORKER_DIR", "worker_dir"),
        ("PYTHON_PREFIX", "python_prefix"),
        ("PYTHON_BASE_PREFIX", "python_base_prefix"),
    ):
        command.extend(("-D", name + "=" + context[key]))
    command.extend((context["python"], "-I", "-B", context["worker"], *arguments))
    try:
        return subprocess.run(
            command, input=input_bytes,
            stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
            timeout=WORKER_WALL_SECONDS, check=False, close_fds=True,
            start_new_session=True, cwd="/",
            env={
                "PATH": "/usr/bin:/bin",
                "HOME": "/var/empty",
                "LANG": "C",
                "PYTHONDONTWRITEBYTECODE": "1",
                "PYTHONNOUSERSITE": "1",
            },
        )
    except (OSError, subprocess.SubprocessError):
        raise MaximumPDFRenderError(BLOCK_MESSAGE) from None


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
    try:
        complete = _run_confined_worker(worker, (str(page_index),), pdf_bytes)
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
