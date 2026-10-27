"""Launch files only after the caller's malware scan gate has accepted them.

Application selection belongs here, not in the ClamAV scan engine. The
user-selectable PDF target defaults to Brave for existing installations.
"""

from pathlib import Path
import os
import re
import stat
import subprocess

PDF_DEFAULT_BUNDLE_ID = "com.brave.Browser"
TARGET_APP_CONFIG = Path.home() / "Library/Application Support/Studio/allow-and-open/target-app.txt"


def pdf_target_application():
    """Return the selected PDF bundle ID, defaulting only when absent."""
    try:
        descriptor = os.open(TARGET_APP_CONFIG, os.O_RDONLY | os.O_NOFOLLOW)
    except FileNotFoundError:
        return PDF_DEFAULT_BUNDLE_ID
    except OSError as error:
        raise RuntimeError("Cannot read the PDF target application setting; opening was stopped.") from error

    try:
        with os.fdopen(descriptor, "rb") as stream:
            if not stat.S_ISREG(os.fstat(stream.fileno()).st_mode):
                raise RuntimeError("The PDF target application setting must be a regular file.")
            value = stream.read(257)
    except OSError as error:
        raise RuntimeError("Cannot read the PDF target application setting; opening was stopped.") from error

    try:
        selected = value.decode("ascii").strip()
    except UnicodeDecodeError:
        selected = ""
    if (len(value) > 256 or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9.-]{1,254}", selected)
            or "." not in selected or ".." in selected
            or selected == "local.studio.brave-pdf-opener"):
        raise RuntimeError("Invalid PDF target application bundle identifier; opening was stopped.")
    return selected


def launch_clean_file(path, target_app=None):
    """Launch an already-approved file with the current destination policy."""
    path = Path(path)
    command = ["/usr/bin/open"]
    if path.suffix.lower() == ".pdf":
        command.extend(["-b", target_app if target_app is not None else pdf_target_application()])
    subprocess.run([*command, str(path)], check=True)
