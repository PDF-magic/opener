#!/usr/bin/env python3
"""Verify both ClamAV commands after provisioning, before installing opener files.

Only fixed scanner locations are considered. The runtime scan gate retains
independent version, signature, quarantine, and file-integrity enforcement.
"""

from pathlib import Path
import re
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from file_launcher import require_executable_path

SCANNER_CANDIDATES = (
    "/opt/homebrew/bin/clamscan",
    "/usr/local/bin/clamscan",
    "/usr/local/clamav/bin/clamscan",
)
VERSION = re.compile(r"^ClamAV (1\.(?:4|5)\.[0-9]+)(?:/|\s|$)")


class DependencyVerificationError(RuntimeError):
    """Fixed, path-free failure description; never expose tool output."""


def command_version(path, *, probe=subprocess.check_output):
    """Query one trusted executable without invoking a scan or parsing stderr."""
    try:
        output = probe([path, "--version"], text=True, timeout=5,
                       stderr=subprocess.DEVNULL)
    except (OSError, subprocess.SubprocessError, UnicodeError, ValueError):
        return None
    if not isinstance(output, str):
        return None
    match = VERSION.match(output.strip())
    return match.group(1) if match else None


def verify_installed_dependencies(*, candidates=SCANNER_CANDIDATES,
                                  validate=require_executable_path,
                                  probe=subprocess.check_output):
    """Return verified versions; fail closed on missing or mismatched tools."""
    scanner = None
    for candidate in candidates:
        try:
            scanner = validate(candidate, allow_symlink=True)
            break
        except RuntimeError:
            continue
    if scanner is None:
        raise DependencyVerificationError(
            "ClamAV scanner is missing or not executable at a supported location. "
            "Install ClamAV and retry."
        )

    # Keep this in the same prefix as the scanner chosen by the runtime gate.
    updater = str(Path(scanner).with_name("freshclam"))
    try:
        validate(updater, allow_symlink=True)
    except RuntimeError:
        raise DependencyVerificationError(
            "The ClamAV signature updater (freshclam) is missing or not executable. "
            "Install a complete ClamAV package and retry."
        ) from None

    scanner_version = command_version(scanner, probe=probe)
    if scanner_version is None:
        raise DependencyVerificationError(
            "The ClamAV scanner version cannot be verified or is unsupported. "
            "Install ClamAV 1.4 or 1.5 and retry."
        )
    updater_version = command_version(updater, probe=probe)
    if updater_version is None:
        raise DependencyVerificationError(
            "The ClamAV signature updater version cannot be verified or is unsupported. "
            "Install a complete ClamAV 1.4 or 1.5 package and retry."
        )
    if scanner_version.split(".")[:2] != updater_version.split(".")[:2]:
        raise DependencyVerificationError(
            "ClamAV scanner and signature updater versions are incompatible. "
            "Install matching ClamAV releases and retry."
        )
    return scanner_version, updater_version


def main():
    try:
        scanner_version, updater_version = verify_installed_dependencies()
    except DependencyVerificationError as error:
        print("ClamAV dependency verification failed: " + str(error),
              file=sys.stderr)
        return 1
    print("Verified ClamAV scanner " + scanner_version
          + " and signature updater " + updater_version + ".")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
