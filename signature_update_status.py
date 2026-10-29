#!/usr/bin/env python3
"""Read installed ClamAV signature update timestamps without running updates.

An update attempt and a successfully completed FreshClam run are separate
facts. Neither timestamp is evidence that a scan is clean or may be skipped.
"""

import datetime
import json
import os
from pathlib import Path
import re
import stat
import time

SIGNATURE_DIRECTORY = (Path.home() / "Library/Application Support/Studio/allow-and-open/signatures")
SUCCESS_STAMP = "last-successful-update"
ATTEMPT_STAMP = "last-attempted-update"
_STAMP_FORMAT = re.compile(rb"[0-9]{1,12}(?:\.[0-9]{1,6})?\n?")


def read_update_time(path, *, now=None):
    """Return a validated UTC datetime or None; never trust symlinked stamps."""
    try:
        # Open only a regular file at the expected path. Avoid following a
        # symlink into user files, devices or otherwise private locations.
        descriptor = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
                             | getattr(os, "O_NONBLOCK", 0))
        try:
            if not stat.S_ISREG(os.fstat(descriptor).st_mode):
                return None
            with os.fdopen(os.dup(descriptor), "rb") as stream:
                raw = stream.read(48)
        finally:
            os.close(descriptor)
        if _STAMP_FORMAT.fullmatch(raw) is None:
            return None
        timestamp = float(raw)
        current = time.time() if now is None else now
        if not 0 < timestamp <= current:
            return None
        return datetime.datetime.fromtimestamp(timestamp, datetime.timezone.utc)
    except (OSError, ValueError, OverflowError, TypeError):
        return None


def read_update_status(signature_directory=SIGNATURE_DIRECTORY, *, now=None):
    """Independent read-only observations, never a guessed last update result."""
    successful = read_update_time(signature_directory / SUCCESS_STAMP, now=now)
    attempted = read_update_time(signature_directory / ATTEMPT_STAMP, now=now)
    return {
        "lastSuccessfulUpdateUtc": successful.isoformat().replace("+00:00", "Z")
        if successful is not None else None,
        "lastAttemptedUpdateUtc": attempted.isoformat().replace("+00:00", "Z")
        if attempted is not None else None,
    }


def main():
    print(json.dumps(read_update_status(), sort_keys=True, allow_nan=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
