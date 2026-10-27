"""Launch files only after the caller's malware scan gate has accepted them.

Application selection belongs here, not in the ClamAV scan engine. Retain the
PDF-to-Brave default while allowing a user-selected PDF bundle ID.
"""

from pathlib import Path
import os
import re
import stat
import subprocess

PDF_DEFAULT_BUNDLE_ID = "com.brave.Browser"
PDF_OPENER_BUNDLE_ID = "local.studio.brave-pdf-opener"
PDF_SYSTEM_DEFAULT_BROWSER = "system-default-browser"
DEFAULT_BROWSER_RESOLVER = Path(__file__).with_name("resolve-default-browser")
PDF_TARGET_VERIFIER = Path(__file__).with_name("verify-pdf-target")


def verify_launch_target(path, target_app=None):
    """Require Launch Services PDF capability for the selected application."""
    if Path(path).suffix.lower() != ".pdf":
        return
    selected = target_app if target_app is not None else intended_destination(path)
    if selected == PDF_OPENER_BUNDLE_ID:
        raise RuntimeError("PDF Magic Opener cannot launch itself; opening was stopped.")
    try:
        completed = subprocess.run(
            [str(PDF_TARGET_VERIFIER), selected],
            capture_output=True, timeout=10,
        )
    except (OSError, subprocess.SubprocessError) as error:
        raise RuntimeError("PDF application support could not be verified; opening was stopped.") from error
    if completed.returncode != 0:
        raise RuntimeError("The selected application is not registered to open PDFs; opening was stopped.")

NATIVE_LAUNCHER = Path(__file__).with_name("launch-scanned-file")
TARGET_APP_CONFIG = Path.home() / "Library/Application Support/Studio/allow-and-open/target-app.txt"


def _valid_bundle_identifier(selected):
    return (bool(re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9.-]{1,254}", selected))
            and "." in selected and ".." not in selected
            and selected != PDF_OPENER_BUNDLE_ID)


def _resolve_default_browser():
    """Pin the current macOS HTTPS handler to one verified destination."""
    try:
        completed = subprocess.run(
            [str(DEFAULT_BROWSER_RESOLVER)],
            capture_output=True, timeout=10, check=True,
        )
        selected = completed.stdout.decode("ascii").strip()
    except (OSError, subprocess.SubprocessError, UnicodeDecodeError, AttributeError) as error:
        raise RuntimeError("The system default browser could not be resolved; opening was stopped.") from error
    if not _valid_bundle_identifier(selected):
        raise RuntimeError("The system default browser is invalid; opening was stopped.")
    return selected


def pdf_target_application():
    """Read an explicit target or resolve the opt-in default browser once."""
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
    if selected == PDF_SYSTEM_DEFAULT_BROWSER and len(value) <= 256:
        return _resolve_default_browser()
    if len(value) > 256 or not _valid_bundle_identifier(selected):
        raise RuntimeError("Invalid PDF target application bundle identifier; opening was stopped.")
    return selected


def intended_destination(path):
    """Describe current launch selection without changing user settings."""
    path = Path(path)
    if path.suffix.lower() == ".pdf":
        return pdf_target_application()
    if path.is_dir() and path.suffix.lower() == ".app":
        return path.name
    return "system-default"


def launch_clean_file(path, target_app=None):
    """Launch an already-approved file with the current destination policy."""
    path = Path(path)
    command = [str(NATIVE_LAUNCHER)]
    if path.suffix.lower() == ".pdf":
        selected = target_app if target_app is not None else pdf_target_application()
        if selected == PDF_OPENER_BUNDLE_ID:
            raise RuntimeError("PDF Magic Opener cannot launch itself; opening was stopped.")
        command.extend(["--bundle-id", selected])
    subprocess.run([*command, str(path)], check=True)
