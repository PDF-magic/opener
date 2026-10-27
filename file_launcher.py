"""Launch files only after the caller's malware scan gate has accepted them.

Application selection belongs here, not in the ClamAV scan engine. Retain the
existing PDF-to-Brave behavior until user-configurable destinations are added.
"""

from pathlib import Path
import subprocess

PDF_DEFAULT_BUNDLE_ID = "com.brave.Browser"
NATIVE_LAUNCHER = Path(__file__).with_name("launch-scanned-file")


def intended_destination(path):
    """Describe current launch selection without changing user settings."""
    path = Path(path)
    if path.suffix.lower() == ".pdf":
        return PDF_DEFAULT_BUNDLE_ID
    if path.is_dir() and path.suffix.lower() == ".app":
        return path.name
    return "system-default"


def launch_clean_file(path):
    """Launch an already-approved file with the current destination policy."""
    path = Path(path)
    command = [str(NATIVE_LAUNCHER)]
    if path.suffix.lower() == ".pdf":
        command.extend(["--bundle-id", PDF_DEFAULT_BUNDLE_ID])
    subprocess.run([*command, str(path)], check=True)
