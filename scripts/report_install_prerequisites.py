#!/usr/bin/env python3
"""Report installer prerequisites without mutating installed files or scanner state.

Homebrew discovery is delegated to the existing opener-0954 detector; this
module only explains whether the install can safely proceed.
"""

import os
from pathlib import Path
import platform
import subprocess
import sys

from detect_homebrew import detect_homebrew


SCANNERS = (
    "/opt/homebrew/bin/clamscan",
    "/usr/local/bin/clamscan",
    "/usr/local/clamav/bin/clamscan",
)
TOOLS = (
    ("/usr/bin/xcrun", "Xcode command-line tools are missing. Run xcode-select --install, then retry."),
    ("/usr/bin/swift", "The Swift command is missing. Install Apple's Xcode command-line tools, then retry."),
    ("/usr/bin/codesign", "The macOS code-signing utility is missing. Restore macOS developer tools, then retry."),
    ("/bin/launchctl", "The macOS LaunchAgent manager is missing. Restore the macOS system tools, then retry."),
)


def executable_file(path):
    """Inspect fixed tool locations only, without running any installed app."""
    return os.path.isfile(path) and os.access(path, os.X_OK)


def swift_compiler_ready():
    """Bounded, read-only command-line toolchain probe; never print raw output."""
    try:
        result = subprocess.run(
            ["/usr/bin/xcrun", "--find", "swiftc"],
            capture_output=True, text=True, timeout=10, check=False,
        )
        return result.returncode == 0 and bool(result.stdout.strip())
    except (OSError, subprocess.SubprocessError):
        return False


def report_prerequisites(*, system, version, workflow_available, executable,
                         compiler_available, scanner_available, homebrew_available):
    """Return fixed, actionable errors and non-blocking notices in stable order."""
    missing = []
    notices = []
    major = version.split(".", 1)[0]
    if system != "darwin":
        missing.append("PDF Magic Opener installation requires macOS 13 or newer.")
    elif not major.isdecimal() or int(major) < 13:
        missing.append("macOS 13 or newer is required; verify or upgrade your macOS version.")
    if not workflow_available:
        missing.append(
            "The Allow and Open Finder Quick Action is missing. "
            "Install the project Finder workflow before retrying."
        )
    for path, message in TOOLS:
        if not executable(path):
            missing.append(message)
    if executable("/usr/bin/xcrun") and not compiler_available:
        missing.append(
            "The Swift compiler is unavailable. Run xcode-select --install "
            "and finish installing the command-line tools before retrying."
        )
    if not scanner_available:
        if not homebrew_available:
            missing.append(
                "ClamAV and Homebrew are unavailable. Install Homebrew or a "
                "supported ClamAV scanner, then retry the installer."
            )
        else:
            notices.append(
                "ClamAV is not installed at a supported location; the installer "
                "will need to provision it through Homebrew."
            )
    return tuple(missing), tuple(notices)


def main():
    workflow = (Path.home() / "Library/Services/Allow and Open.workflow"
                / "Contents/document.wflow")
    scanner_available = any(executable_file(path) for path in SCANNERS)
    missing, notices = report_prerequisites(
        system=sys.platform,
        version=platform.mac_ver()[0],
        workflow_available=workflow.is_file(),
        executable=executable_file,
        compiler_available=swift_compiler_ready()
        if executable_file("/usr/bin/xcrun") else False,
        scanner_available=scanner_available,
        homebrew_available=True if scanner_available else detect_homebrew() is not None,
    )
    for notice in notices:
        print("Installation prerequisite notice: " + notice)
    if missing:
        print("Cannot install PDF Magic Opener; missing prerequisites:", file=sys.stderr)
        for explanation in missing:
            print(" - " + explanation, file=sys.stderr)
        print("No installation changes were made by this prerequisite check.", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
