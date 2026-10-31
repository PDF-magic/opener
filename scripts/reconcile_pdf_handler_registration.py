#!/usr/bin/env python3
"""Conservatively reconcile the verified PDF opener's Launch Services registration."""

import json
from pathlib import Path
import subprocess
import sys

LSREGISTER = ("/System/Library/Frameworks/CoreServices.framework/Frameworks/"
              "LaunchServices.framework/Support/lsregister")


class RegistrationConflict(RuntimeError):
    pass


def check_registrations(paths, installed, legacy):
    """Only an absent legacy alias may be withdrawn, never another live app."""
    if not isinstance(paths, list) or any(not isinstance(p, str) for p in paths):
        raise RegistrationConflict("Invalid PDF opener registration inventory.")
    seen = set()
    stale = []
    for text in paths:
        path = Path(text)
        if not path.is_absolute() or str(path) != text or text in seen:
            raise RegistrationConflict("Invalid or duplicate PDF opener registration.")
        seen.add(text)
        if path == installed:
            continue
        if path == legacy and not path.exists() and not path.is_symlink():
            stale.append(path)
            continue
        raise RegistrationConflict("Another PDF opener registration exists; no change made.")
    return stale


def reconcile(installed, legacy, *, lookup, run):
    if installed.name != "PDF Magic Opener.app" or legacy.name != "Open PDFs in Brave.app":
        raise RegistrationConflict("Unexpected PDF opener bundle names.")
    if installed.parent != legacy.parent or not installed.is_dir() or installed.is_symlink():
        raise RegistrationConflict("Installed PDF opener bundle is unavailable or unsafe.")
    stale = check_registrations(lookup(), installed, legacy)
    # Ensure there is a registered working replacement before withdrawing the alias.
    run([LSREGISTER, "-f", str(installed)], check=True, timeout=30)
    for path in stale:
        run([LSREGISTER, "-u", str(path)], check=True, timeout=30)
    if lookup() != [str(installed)]:
        raise RegistrationConflict("PDF opener registrations did not converge to one bundle.")


def registered_paths(enumerator):
    result = subprocess.run(["/usr/bin/swift", str(enumerator)], check=True, timeout=60,
                            capture_output=True, text=True)
    try:
        return json.loads(result.stdout)
    except (ValueError, TypeError) as error:
        raise RegistrationConflict("Cannot decode PDF opener registrations.") from error


def main():
    if len(sys.argv) != 4:
        raise SystemExit("Expected installed app, legacy app, and registration enumerator.")
    installed, legacy, enumerator = map(Path, sys.argv[1:])
    home_apps = Path.home() / "Applications"
    if (installed != home_apps / "PDF Magic Opener.app"
            or legacy != home_apps / "Open PDFs in Brave.app"):
        raise SystemExit("Refusing to change registration outside the managed app location.")
    try:
        reconcile(installed, legacy, lookup=lambda: registered_paths(enumerator),
                  run=subprocess.run)
    except (RegistrationConflict, OSError, subprocess.SubprocessError) as error:
        raise SystemExit(f"PDF opener registration reconciliation failed: {error}") from error


if __name__ == "__main__":
    main()
