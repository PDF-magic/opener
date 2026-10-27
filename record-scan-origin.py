#!/usr/bin/env python3
"""Record local scan-request origin flags without logging document identities."""
import json
import os
from pathlib import Path
import stat
import sys
import time

ORIGIN_LOG = (Path.home() / 'Library/Application Support/Studio/allow-and-open'
              / 'scan-request-origins.jsonl')
ORIGIN_ENV = 'PDF_MAGIC_REQUEST_ORIGIN'


def origin_flags(source):
    """Unknown sources are deliberately not assigned to any origin category."""
    return {
        'from_finder': source == 'finder',
        'from_browser': source == 'browser',
        'from_desktop_application': source == 'desktop-application',
    }


def record_origins(source, count=1, path=None):
    """Append one anonymous origin record per selected item; never affect scanning."""
    if count < 1:
        return False
    path = path if path is not None else ORIGIN_LOG
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        flags = origin_flags(source)
        lines = ''.join(json.dumps({'requested_at': time.time(), **flags}) + '\n'
                        for _ in range(count))
        options = (os.O_WRONLY | os.O_APPEND | os.O_CREAT | os.O_NONBLOCK
                   | os.O_CLOEXEC | os.O_NOFOLLOW)
        fd = os.open(path, options, 0o600)
        try:
            details = os.fstat(fd)
            # Do not append to links, devices, other users' files, or public files.
            if (not stat.S_ISREG(details.st_mode) or details.st_nlink != 1
                    or details.st_uid != os.getuid() or details.st_mode & 0o077):
                return False
            with os.fdopen(fd, 'a', encoding='utf-8') as stream:
                fd = -1
                stream.write(lines)
            return True
        finally:
            if fd >= 0:
                os.close(fd)
    except OSError:
        # Metadata collection must never weaken or block the malware scan gate.
        return False


def main(paths):
    record_origins(os.environ.get(ORIGIN_ENV), len(paths))
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
