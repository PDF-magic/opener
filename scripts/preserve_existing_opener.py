#!/usr/bin/env python3
"""Snapshot only overwritten opener executables for failed-installation recovery.

This deliberately excludes FreshClam configuration, signature databases, selected
browser settings, user documents, and the Finder workflow's historical backup.
"""
import argparse
import json
import os
from pathlib import Path
import shutil
import stat

# Exactly the fixed program paths overwritten by install-allow-and-open.sh.
PROGRAMS = (
    "allow-and-open.sh", "scan-and-open.py", "file_launcher.py",
    "browser_registry.py", "scan_results.py", "record-scan-origin.py",
    "update-malware-signatures.sh", "signature_update_status.py",
    "pdf-handler-status.py", "launch-scanned-file", "resolve-default-browser",
    "discover-installed-browsers", "installed-applications", "identify-pdf-handler",
    "detect-pdf-handler-change", "pdf-handler-history", "verify-pdf-target",
    "select-custom-pdf-application.py", "select-custom-pdf-application",
    "browser-preference-list",
)
MANIFEST = "snapshot.json"


def checked_directory(directory):
    if directory.is_symlink() or (directory.exists() and not directory.is_dir()):
        raise ValueError("Unsafe opener executable directory")


def checked_file(path):
    if path.is_symlink():
        raise ValueError("Unsafe opener program symlink")
    try:
        descriptor = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
    except FileNotFoundError:
        return None, None
    metadata = os.fstat(descriptor)
    if not stat.S_ISREG(metadata.st_mode) or metadata.st_nlink != 1:
        os.close(descriptor)
        raise ValueError("Unsafe existing opener program file")
    return descriptor, metadata


def snapshot(install, backup):
    checked_directory(install)
    checked_directory(backup)
    if not backup.is_dir() or (backup / MANIFEST).exists():
        raise ValueError("Missing or reused private recovery directory")
    states = {}
    for name in PROGRAMS:
        descriptor, metadata = checked_file(install / name)
        states[name] = descriptor is not None
        if descriptor is None:
            continue
        with os.fdopen(descriptor, "rb") as original, (backup / name).open("xb") as saved:
            shutil.copyfileobj(original, saved)
            saved.flush()
            os.fsync(saved.fileno())
        (backup / name).chmod(stat.S_IMODE(metadata.st_mode))
        os.utime(backup / name, ns=(metadata.st_atime_ns, metadata.st_mtime_ns))
    with (backup / MANIFEST).open("x", encoding="utf-8") as stream:
        json.dump(states, stream)
        stream.flush()
        os.fsync(stream.fileno())


def restore(install, backup):
    checked_directory(install)
    checked_directory(backup)
    with (backup / MANIFEST).open("r", encoding="utf-8") as stream:
        states = json.load(stream)
    if (not isinstance(states, dict) or set(states) != set(PROGRAMS)
            or any(type(value) is not bool for value in states.values())):
        raise ValueError("Invalid opener recovery manifest")
    # Refuse all unsafe destinations before changing any file.
    for name, existed in states.items():
        destination = install / name
        if destination.is_symlink() or (destination.exists() and (
                not destination.is_file() or destination.stat().st_nlink != 1)):
            raise ValueError("Unsafe opener program changed during migration")
        if existed:
            saved = backup / name
            descriptor, metadata = checked_file(saved)
            if descriptor is None:
                raise ValueError("Missing original opener program in recovery staging")
            os.close(descriptor)
    if not install.exists():
        install.mkdir(parents=True)
    for name, existed in states.items():
        destination = install / name
        if existed:
            os.replace(backup / name, destination)
        elif destination.exists():
            destination.unlink()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("snapshot", "restore"))
    parser.add_argument("install", type=Path)
    parser.add_argument("backup", type=Path)
    arguments = parser.parse_args()
    try:
        (snapshot if arguments.action == "snapshot" else restore)(
            arguments.install, arguments.backup
        )
    except (OSError, ValueError, json.JSONDecodeError) as error:
        parser.exit(1, f"Opener installation recovery refused: {error}\n")


if __name__ == "__main__":
    main()
