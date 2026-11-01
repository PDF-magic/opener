#!/usr/bin/env python3
"""Opt-in removal of verified abandoned PDF Magic temporary PDFs on uninstall.

Run from a trusted checkout only after disconnecting entry points, stopping
PDF Magic processes and closing viewers using staged PDF copies. No caller
paths, symlinks, browser downloads, preferences or scanner data are removed.
"""
import argparse
import sys

from maximum_temporary_output import (
    MaximumTemporaryOutputError,
    cleanup_uninstall_temporary_pdfs,
)

REFUSAL = "Temporary PDF uninstall cleanup refused; no unverified files were removed."


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--remove", action="store_true",
        help="explicitly remove verified, abandoned application-private temporary PDFs",
    )
    args = parser.parse_args(argv)
    if not args.remove:
        print("No temporary files changed. Use --remove only after closing PDF viewers.")
        return 0
    if not sys.stdin.isatty():
        print(REFUSAL, file=sys.stderr)
        return 2
    try:
        approval = input(
            "After stopping PDF Magic and closing all staged-PDF viewers, "
            "type REMOVE to clean verified abandoned PDFs: "
        )
    except (EOFError, KeyboardInterrupt):
        print(REFUSAL, file=sys.stderr)
        return 2
    if approval != "REMOVE":
        print(REFUSAL, file=sys.stderr)
        return 2
    try:
        removed = cleanup_uninstall_temporary_pdfs()
    except MaximumTemporaryOutputError:
        print(REFUSAL, file=sys.stderr)
        return 1
    print(
        f"Removed {removed} verified abandoned PDF Magic temporary PDF(s). "
        "Active or unrecognized entries, and all user data, were retained."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
