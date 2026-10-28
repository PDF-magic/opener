#!/usr/bin/env python3
"""Read-only browser selector populated by supplied installation discovery results.

The user-facing menu only returns a chosen bundle identifier. It never writes
target-app.txt, changes the macOS default, or opens an application. Discovery
itself is a separate installed-applications checklist requirement.
"""

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

MAX_DISCOVERY_BYTES = 256 * 1024
MAX_BROWSER_RESULTS = 2048
OPENER_BUNDLE_ID = "local.studio.brave-pdf-opener"
# Reuse the installed, read-only HTTPS default-browser resolver. Do not query
# PDF associations: PDF Magic Opener may itself be the default PDF handler.
DEFAULT_BROWSER_RESOLVER = (Path.home() /
    "Library/Application Support/Studio/allow-and-open/resolve-default-browser")
BUNDLE_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9.-]{1,254}\Z")


def selector_choices(discovery_results):
    """Return sorted (display name, bundle ID) options from installed results.

    Each browser record has a bundle_id, name, and boolean installed field.
    Different installations with one bundle ID are a single preference choice:
    the existing target-app.txt format addresses a bundle, not a path.
    """
    if isinstance(discovery_results, dict):
        discovery_results = discovery_results.get("browsers")
    if not isinstance(discovery_results, list) or len(discovery_results) > MAX_BROWSER_RESULTS:
        raise ValueError("Invalid browser discovery results")

    found = {}
    for entry in discovery_results:
        if not isinstance(entry, dict) or entry.get("installed") is not True:
            continue
        bundle_id = entry.get("bundle_id")
        if (not isinstance(bundle_id, str) or not BUNDLE_ID.fullmatch(bundle_id)
                or "." not in bundle_id or ".." in bundle_id
                or bundle_id == OPENER_BUNDLE_ID):
            continue
        name = entry.get("name")
        if (not isinstance(name, str) or not 0 < len(name.strip()) <= 100
                or any(ord(ch) < 32 or ord(ch) == 127 for ch in name)):
            name = bundle_id
        previous = found.get(bundle_id)
        if previous is None or (name.casefold(), name) < (previous.casefold(), previous):
            found[bundle_id] = name
    return tuple(sorted(((name, bundle_id) for bundle_id, name in found.items()),
                        key=lambda item: (item[0].casefold(), item[1])))


def system_default_browser():
    """Read the macOS default web browser without changing any preferences.

    An absent, failing, or malformed resolver means no browser gets the marker;
    it never substitutes a different browser or modifies discovery results.
    """
    try:
        completed = subprocess.run(
            [str(DEFAULT_BROWSER_RESOLVER)], capture_output=True, text=True,
            check=True, timeout=5,
        )
    except (OSError, subprocess.SubprocessError, UnicodeError):
        return None
    identifier = completed.stdout.strip()
    if (not BUNDLE_ID.fullmatch(identifier) or "." not in identifier
            or ".." in identifier or identifier == OPENER_BUNDLE_ID):
        return None
    return identifier


def choose_browser(choices, current=None, *, system_default=None,
                   source=None, destination=None):
    """Show discovered choices; return one bundle ID only on explicit selection."""
    source = source or sys.stdin
    destination = destination or sys.stderr
    if not choices:
        print("No installed browsers were found in discovery results.", file=destination)
        return None
    for index, (name, bundle_id) in enumerate(choices, start=1):
        marker = " (current)" if bundle_id == current else ""
        default_marker = " (system default)" if bundle_id == system_default else ""
        print(f"{index}. {name} [{bundle_id}]{marker}{default_marker}", file=destination)
    print("Choose a browser number (Enter or q to cancel): ", end="", file=destination,
          flush=True)
    answer = source.readline().strip()
    if answer.lower() == "q" or not answer or not answer.isascii() or not answer.isdecimal():
        return None
    number = int(answer)
    return choices[number - 1][1] if 1 <= number <= len(choices) else None


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--current", help="Existing preferred browser bundle identifier")
    args = parser.parse_args(argv)
    # Accept bounded discovery data only on stdin; do not inspect user settings.
    payload = sys.stdin.buffer.read(MAX_DISCOVERY_BYTES + 1)
    if len(payload) > MAX_DISCOVERY_BYTES:
        print("Browser discovery results are too large.", file=sys.stderr)
        return 1
    try:
        choices = selector_choices(json.loads(payload))
    except (ValueError, UnicodeDecodeError, TypeError):
        print("Invalid browser discovery results.", file=sys.stderr)
        return 1
    # Selection input must come from a controlling terminal, not discovery data.
    try:
        with open("/dev/tty", "r", encoding="utf-8") as keyboard:
            selected = choose_browser(
                choices, current=args.current,
                system_default=system_default_browser(), source=keyboard)
    except OSError:
        print("Interactive terminal is required to choose a browser.", file=sys.stderr)
        return 1
    if selected is None:
        return 1
    print(selected)
    return 0


if __name__ == "__main__":
    sys.exit(main())
