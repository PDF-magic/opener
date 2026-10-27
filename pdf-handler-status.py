#!/usr/bin/env python3
"""Read-only current macOS PDF default-handler status."""

from pathlib import Path
import re
import subprocess
import sys

OPENER_BUNDLE_ID = "local.studio.brave-pdf-opener"
HANDLER_LOOKUP = Path(__file__).with_name("identify-pdf-handler")
LOOKUP_ERROR = "The current macOS PDF handler status could not be determined."


def current_pdf_handler():
    """Ask the existing PDF-specific helper, never the HTTPS browser resolver."""
    try:
        result = subprocess.run(
            [str(HANDLER_LOOKUP)], capture_output=True, check=True, timeout=10
        )
        raw = result.stdout
        if not isinstance(raw, bytes) or len(raw) > 256:
            raise ValueError("Invalid handler output")
        text = raw.decode("ascii")
        if not text.endswith("\n"):
            raise ValueError("Missing output terminator")
        identifier = text[:-1]
        if (not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9.-]{1,254}", identifier)
                or "." not in identifier or ".." in identifier):
            raise ValueError("Invalid handler identifier")
        return identifier
    except (OSError, subprocess.SubprocessError, UnicodeError, ValueError) as error:
        raise RuntimeError(LOOKUP_ERROR) from error


def status_message(identifier):
    """Report the current association without changing it."""
    if identifier == OPENER_BUNDLE_ID:
        return (f"Current macOS PDF handler: PDF Magic Opener ({identifier})\n"
                "PDF Magic Opener is the default PDF handler.")
    return (f"Current macOS PDF handler: {identifier}\n"
            "PDF Magic Opener is not the default PDF handler.")


def main(args=None):
    if args is None:
        args = sys.argv[1:]
    if args:
        print("Usage: pdf-handler-status.py", file=sys.stderr)
        return 2
    try:
        print(status_message(current_pdf_handler()))
    except RuntimeError:
        print(LOOKUP_ERROR, file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
