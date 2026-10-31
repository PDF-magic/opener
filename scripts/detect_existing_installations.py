#!/usr/bin/env python3
"""Read-only discovery of previously installed PDF Magic Opener applications.

This inventory is not authorization to migrate, replace, or launch an app.
Install/migration decisions must separately verify the selected bundle.
"""

import argparse
import json
from pathlib import Path
import plistlib

LEGACY_APP_NAME = "Open PDFs in Brave.app"
APPLICATION_NAMES = frozenset((LEGACY_APP_NAME, "PDF Magic Opener.app", "PDFMagicOpener.app"))
APPLICATION_IDENTIFIERS = frozenset((
    "local.studio.brave-pdf-opener",
    "local.studio.pdfmagicopener.swiftui",
))
MAX_PLIST_BYTES = 256 * 1024


def _bundle_identifier(app):
    """Read small, regular Info.plist files without following bundle symlinks."""
    contents = app / "Contents"
    info = contents / "Info.plist"
    if (app.is_symlink() or not app.is_dir() or contents.is_symlink()
            or not contents.is_dir() or info.is_symlink() or not info.is_file()):
        return None
    try:
        if info.stat().st_size > MAX_PLIST_BYTES:
            return None
        with info.open("rb") as stream:
            value = plistlib.load(stream)
        identifier = value.get("CFBundleIdentifier") if isinstance(value, dict) else None
        return identifier if isinstance(identifier, str) else None
    except (OSError, ValueError, TypeError, plistlib.InvalidFileException):
        return None


def detect_existing_installations(application_directories=None):
    """Inventory known application IDs and named candidates; never modify disk.

    Only immediate .app children of ~/Applications and /Applications are read.
    Unknown apps are not reported unless they occupy a recognized app name.
    """
    if application_directories is None:
        application_directories = (Path.home() / "Applications", Path("/Applications"))
    results = []
    visited = set()
    for directory in application_directories:
        directory = Path(directory)
        if directory.is_symlink() or not directory.is_dir():
            continue
        try:
            apps = sorted(directory.iterdir(), key=lambda item: item.name)
        except OSError:
            continue
        for app in apps:
            if not app.name.endswith(".app") or str(app) in visited:
                continue
            visited.add(str(app))
            identifier = _bundle_identifier(app)
            named_candidate = app.name in APPLICATION_NAMES
            if identifier not in APPLICATION_IDENTIFIERS and not named_candidate:
                continue
            results.append({
                "path": str(app),
                "name": app.name,
                "bundle_identifier": identifier if isinstance(identifier, str) else None,
                "status": ("recognized" if identifier in APPLICATION_IDENTIFIERS
                           else "unverified_candidate"),
                "legacy_name": app.name == LEGACY_APP_NAME,
            })
    return results


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--applications-dir", action="append", type=Path,
                        help="Limit discovery to these application directories (repeatable)")
    args = parser.parse_args()
    print(json.dumps(detect_existing_installations(args.applications_dir), indent=2))


if __name__ == "__main__":
    main()
