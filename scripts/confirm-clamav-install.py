#!/usr/bin/env python3
"""Require interactive, explicit consent before a ClamAV Homebrew install.

No environment flag, redirected stdin, or noninteractive invocation can
approve a package-manager operation. This file never launches subprocesses.
"""

import sys


PROMPT = (
    "\nClamAV is not installed in a supported scanner location.\n"
    "To continue, the installer would execute: brew install clamav\n"
    "Homebrew may download packages, modify its managed prefix, or request\n"
    "administrator authorization. Homebrew will not be installed or upgraded\n"
    "by this installer. You may cancel and install ClamAV separately.\n"
    "Type INSTALL to authorize this ClamAV Homebrew command (anything else cancels): "
)
REFUSAL = (
    "ClamAV installation was not authorized. Install ClamAV yourself "
    "(for example, run brew install clamav), then rerun the installer."
)


def confirm_installation(terminal=None):
    """Authorize only a clearly disclosed command on a real TTY."""
    if terminal is not None:
        return _ask(terminal)

    try:
        # Never accept piped input as consent; require a controlling terminal.
        with open("/dev/tty", "r+", encoding="utf-8") as console:
            return _ask(console)
    except (OSError, UnicodeError):
        return False


def _ask(console):
    if not console.isatty():
        return False
    try:
        console.write(PROMPT)
        console.flush()
        # Bound input and require a full line. "INSTALL" without Return,
        # prefixes, suffixes, or whitespace must not authorize anything.
        return console.readline(16) == "INSTALL\n"
    except (OSError, UnicodeError):
        return False


def main():
    if len(sys.argv) != 1 or not confirm_installation():
        print(REFUSAL, file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
