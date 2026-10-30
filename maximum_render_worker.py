"""Private bounded raster worker for planned Maximum PDF protection.

Never import this through the deployed scanner or a PDF preview handler. It
receives a PDF in memory and emits exactly one framed PNG page (opener-0314).
"""

import json
import math
import os
import struct
import sys


def main() -> int:
    if (len(sys.argv) != 2 or
            not sys.argv[1].isascii() or
            not sys.argv[1].isdecimal() or
            sys.argv[1] != str(int(sys.argv[1]))):
        return 2
    # Python -I omits the script directory. Restore only this trusted module
    # path, not the process cwd or user PYTHONPATH.
    sys.path.insert(0, os.path.dirname(os.path.realpath(__file__)))

    from maximum_isolated_worker import _apply_limits
    _apply_limits()  # OS CPU/memory/no-file limits BEFORE importing renderer.

    if sys.platform == "linux":
        from maximum_network_isolation import (
            apply_linux_child_process_denial, apply_linux_network_denial,
        )
        apply_linux_network_denial()
        apply_linux_child_process_denial()
        # Linux currently lacks the parent-enforced renderer filesystem
        # allowlist. Never read untrusted bytes or import MuPDF without it.
        return 2
    elif (sys.platform != "darwin" or
          os.environ.get("PDF_MAGIC_RENDER_NETWORK_SANDBOX") != "seatbelt-v1"):
        # macOS must be launched through the parent's sandbox-exec wrapper.
        return 2

    from pathlib import Path
    from maximum_isolated_renderer import (
        MAGIC, MAX_DOCUMENT_PAGES, MAX_METADATA_BYTES, MAX_PDF_BYTES,
        MAX_PNG_BYTES, MAX_RENDER_PIXELS, MAX_RENDER_SIDE,
        _renderer_sandbox_context, apply_renderer_sandbox,
    )
    context = _renderer_sandbox_context(Path(__file__).resolve())
    apply_renderer_sandbox(context)

    index = int(sys.argv[1])
    if not 0 <= index < MAX_DOCUMENT_PAGES:
        return 2
    document_bytes = sys.stdin.buffer.read(MAX_PDF_BYTES + 1)
    if not 0 < len(document_bytes) <= MAX_PDF_BYTES:
        return 2

    import pymupdf

    doc = pymupdf.open(stream=document_bytes, filetype="pdf")
    try:
        if (not doc.is_pdf or doc.needs_pass or
                not 1 <= doc.page_count <= MAX_DOCUMENT_PAGES or
                index >= doc.page_count):
            return 2
        page = doc.load_page(index)
        bounds = page.rect
        width, height = float(bounds.width), float(bounds.height)
        if (not math.isfinite(width) or not math.isfinite(height) or
                not 0 < width <= 100_000 or not 0 < height <= 100_000):
            return 2
        # Prevent unbounded native allocations BEFORE rendering. No user-DPI
        # option and no high-resolution or annotation/script execution.
        scale = min(1.0, MAX_RENDER_SIDE / width, MAX_RENDER_SIDE / height)
        pix = page.get_pixmap(
            matrix=pymupdf.Matrix(scale, scale), colorspace=pymupdf.csRGB,
            alpha=False, annots=False,
        )
        if (not 1 <= pix.width <= MAX_RENDER_SIDE or
                not 1 <= pix.height <= MAX_RENDER_SIDE or
                pix.width * pix.height > MAX_RENDER_PIXELS or
                pix.n != 3):
            return 2
        png = pix.tobytes("png")
        if not 33 <= len(png) <= MAX_PNG_BYTES:
            return 2
        # Only fixed numeric metadata passes to the parent, never PDF strings.
        meta = json.dumps({
            "version": 1,
            "pageIndex": index,
            "pageCount": doc.page_count,
            "width": pix.width,
            "height": pix.height,
            "workerPid": os.getpid(),
            "permitsOpen": False,
        }, separators=(",", ":")).encode("ascii")
        if not 0 < len(meta) <= MAX_METADATA_BYTES:
            return 2
        payload = struct.pack(">8sII", MAGIC, len(meta), len(png))
        sys.stdout.buffer.write(payload + meta + png)
        sys.stdout.buffer.flush()
        return 0
    finally:
        doc.close()


if __name__ == "__main__":
    try:
        code = main()
    except BaseException:
        # No PDF-controlled diagnostics or partial raster output on failure.
        code = 2
    finally:
        # The macOS memory watchdog must remain active for all parsing and
        # rasterization, but must be disarmed before interpreter teardown.
        # Otherwise a late SIGALRM may terminate a worker *after* it has
        # emitted a valid PNG, creating nondeterministic false failures.
        if sys.platform == "darwin":
            try:
                import signal
                signal.setitimer(signal.ITIMER_REAL, 0)
            except BaseException:
                code = 2
    raise SystemExit(code)
