#!/usr/bin/env python3
"""Interactively verify the replacement macOS PDF viewer after uninstall.

Never changes file associations or opens a user's PDF. The only document opened
is a newly generated, benign, single-page PDF in a private temporary folder.
"""

import os
from pathlib import Path
import subprocess
import sys
from tempfile import TemporaryDirectory


OPEN_TOOL = "/usr/bin/open"
PROMPT = (
    "Did your chosen OTHER PDF application (not PDF Magic Opener) display "
    "the test page? [y/N] "
)


def sample_pdf():
    """Build a tiny valid PDF with exact cross-reference offsets, no input files."""
    stream = b"BT /F1 18 Tf 72 720 Td (PDF viewer verification) Tj ET\n"
    objects = (
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] "
        b"/Resources << /Font << /F1 5 0 R >> >> /Contents 4 0 R >>",
        b"<< /Length " + str(len(stream)).encode("ascii")
        + b" >>\nstream\n" + stream + b"endstream",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
    )
    content = bytearray(b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n")
    offsets = [0]
    for index, item in enumerate(objects, start=1):
        offsets.append(len(content))
        content.extend(f"{index} 0 obj\n".encode("ascii") + item + b"\nendobj\n")
    startxref = len(content)
    content.extend(f"xref\n0 {len(offsets)}\n0000000000 65535 f \n".encode("ascii"))
    for offset in offsets[1:]:
        content.extend(f"{offset:010} 00000 n \n".encode("ascii"))
    content.extend(
        b"trailer\n<< /Size 6 /Root 1 0 R >>\nstartxref\n"
        + str(startxref).encode("ascii") + b"\n%%EOF\n"
    )
    return bytes(content)


def verify(*, platform, interactive, launch, ask, say, error):
    """Use the system default-opening route, then require a human visual check."""
    if platform != "darwin" or not interactive:
        error("Verification requires an interactive macOS Terminal session.")
        return 2

    with TemporaryDirectory(prefix="pdf-magic-viewer-check-") as folder:
        document = Path(folder) / "pdf-viewer-check.pdf"
        descriptor = os.open(document, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(descriptor, "wb") as output:
            output.write(sample_pdf())
        try:
            # No -a/-b override: Launch Services must use the actual PDF default.
            launch([OPEN_TOOL, str(document)], check=True, timeout=20,
                   stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        except (OSError, subprocess.SubprocessError):
            error("macOS could not dispatch the test PDF to its default viewer.")
            return 1

        try:
            answer = ask(PROMPT)
        except (EOFError, KeyboardInterrupt):
            error("No viewer confirmation received; verification failed.")
            return 1
        if answer.strip().lower() not in ("y", "yes"):
            error("Replacement PDF opening was not confirmed; do not mark uninstall complete.")
            return 1
        say("Verified: another application displayed a PDF via the macOS default route.")
        return 0


def main(argv=None):
    if argv is None:
        argv = sys.argv[1:]
    if argv != ["--live"]:
        print("Usage: python3 verify-other-pdf-open.py --live", file=sys.stderr)
        return 2
    return verify(platform=sys.platform, interactive=sys.stdin.isatty(),
                  launch=subprocess.run, ask=input, say=print,
                  error=lambda message: print(message, file=sys.stderr))


if __name__ == "__main__":
    sys.exit(main())
