#!/usr/bin/env python3
"""Read-only detection of the signature database from an existing installation.

Detection is not validation: the scanner and staged updater separately enforce
signature freshness, database loading, and their fail-closed admission rules.
"""

import os
from pathlib import Path
import stat
import sys


INSTALL_SIGNATURE_DIRECTORY = (
    Path.home() / "Library/Application Support/Studio/allow-and-open/signatures"
)


def detect_existing_signature_database(directory=INSTALL_SIGNATURE_DIRECTORY):
    """Return 'existing', 'missing', 'incomplete', or 'unsafe' without writes.

    A complete database has exactly one nonempty regular .cvd/.cld file for
    each of main and daily. This does not assert freshness or authenticity.
    """
    directory = Path(directory)
    try:
        root = os.lstat(directory)
    except FileNotFoundError:
        return "missing"
    except OSError:
        return "unsafe"
    if not stat.S_ISDIR(root.st_mode):
        return "unsafe"

    counts = []
    incomplete = False
    for name in ("main", "daily"):
        count = 0
        for suffix in (".cvd", ".cld"):
            try:
                entry = os.lstat(directory / (name + suffix))
            except FileNotFoundError:
                continue
            except OSError:
                return "unsafe"
            if not stat.S_ISREG(entry.st_mode):
                return "unsafe"
            if entry.st_size == 0:
                incomplete = True
            else:
                count += 1
        counts.append(count)
    return "existing" if counts == [1, 1] and not incomplete else "incomplete"


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    if len(argv) > 1:
        print("Expected at most one signature directory argument.", file=sys.stderr)
        return 2
    status = detect_existing_signature_database(
        Path(argv[0]) if argv else INSTALL_SIGNATURE_DIRECTORY
    )
    if status == "unsafe":
        print("Existing signature location is unsafe; installation stopped.", file=sys.stderr)
        return 1
    messages = {
        "existing": "Existing ClamAV signature database found; update validation is still required.",
        "incomplete": "Existing ClamAV signature directory is incomplete; update required.",
        "missing": "No existing ClamAV signature database found.",
    }
    print(messages[status])
    return 0


if __name__ == "__main__":
    sys.exit(main())
