#!/usr/bin/env python3
"""Offer (never silently apply) restoration of PDF Magic Opener's PDF association."""

import re
import subprocess
import sys

OPENER_ID = "local.studio.brave-pdf-opener"
VALID_BUNDLE = re.compile(r"[A-Za-z0-9]+(?:[.-][A-Za-z0-9]+)+")


def offer_restore(identifier, setter, app, *, run=subprocess.run,
                  interactive=None, ask=input, say=print):
    """Inspect the PDF handler and require affirmative user consent to replace it."""
    try:
        result = run([identifier], capture_output=True, text=True,
                     check=True, timeout=10)
    except (OSError, subprocess.SubprocessError):
        say("Cannot verify the current PDF handler; leaving macOS defaults unchanged.")
        return False

    # Reject ambiguous, multiline, and malformed lookup results rather than
    # changing an association whose current owner cannot be established.
    observed = result.stdout.strip()
    if not VALID_BUNDLE.fullmatch(observed) or result.stdout.strip("\r\n") != observed:
        say("Cannot verify the current PDF handler; leaving macOS defaults unchanged.")
        return False
    if observed == OPENER_ID:
        say("PDF Magic Opener is already the default PDF application.")
        return False

    if interactive is None:
        interactive = sys.stdin.isatty()
    if not interactive:
        say("A different application is the default for PDFs. "
            "No changes made; rerun the installer interactively to be offered restoration.")
        return False

    try:
        answer = ask("Restore PDF Magic Opener as the default PDF application? [y/N] ")
    except EOFError:
        answer = ""
    if answer.strip().lower() not in ("y", "yes"):
        say("Keeping the existing default PDF application.")
        return False

    # Use the existing setter only after explicit affirmative consent, and
    # keep the separate post-scan PDF destination preference untouched.
    run(["/usr/bin/swift", setter, app], check=True, timeout=120)
    return True


def main():
    if len(sys.argv) != 4:
        raise SystemExit("Expected installed handler reader, setter, and opener app.")
    offer_restore(*sys.argv[1:])


if __name__ == "__main__":
    main()
