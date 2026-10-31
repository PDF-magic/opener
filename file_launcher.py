"""Launch files only after the caller's malware scan gate has accepted them.

Application selection belongs here, not in the ClamAV scan engine. Retain the
PDF-to-Brave default while allowing a user-selected PDF bundle ID.
"""

from browser_registry import DEFAULT_BROWSER_BUNDLE_ID
from contextlib import contextmanager
from contextvars import ContextVar
from pathlib import Path
import os
import re
import stat
import subprocess
import sys

PDF_DEFAULT_BUNDLE_ID = DEFAULT_BROWSER_BUNDLE_ID
PDF_OPENER_BUNDLE_ID = "local.studio.brave-pdf-opener"
PDF_SYSTEM_DEFAULT_BROWSER = "system-default-browser"
DEFAULT_BROWSER_RESOLVER = Path(__file__).with_name("resolve-default-browser")
PDF_TARGET_VERIFIER = Path(__file__).with_name("verify-pdf-target")

PDF_TARGET_UNAVAILABLE_MESSAGE = (
    "The selected PDF application is unavailable or cannot open PDFs. "
    "Install it or choose an installed PDF-capable application in target-app.txt; opening was stopped."
)
PDF_TARGET_VERIFICATION_MESSAGE = (
    "PDF application availability could not be checked. "
    "Reinstall PDF Magic Opener and try again; opening was stopped."
)
PDF_DEFAULT_BROWSER_UNAVAILABLE_MESSAGE = (
    "The macOS default browser is unavailable or could not be resolved. "
    "Choose an installed default browser in System Settings, or select an installed "
    "PDF-capable application in target-app.txt; opening was stopped."
)


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
        raise RuntimeError(PDF_TARGET_VERIFICATION_MESSAGE) from error
    if completed.returncode != 0:
        raise RuntimeError(PDF_TARGET_UNAVAILABLE_MESSAGE)

NATIVE_LAUNCHER = Path(__file__).with_name("launch-scanned-file")

# Each scan's proof belongs only to that request and never to persistent settings.
_APPROVED_FILE_IDENTITY = ContextVar("approved_file_identity", default=None)


@contextmanager
def scanned_file_identity(identity):
    """Pin the scanned root's filesystem identity for the native handoff.

    The scanner separately checks all .app members and file bytes. A context
    variable isolates concurrent requests and preserves the launch API.
    """
    if (not isinstance(identity, tuple) or not identity
            or not isinstance(identity[0], tuple) or len(identity[0]) != 7
            or identity[0][0] != ""
            or any(type(value) is not int for value in identity[0][1:])):
        raise RuntimeError("The scanned file identity is invalid; opening was stopped.")
    proof = ":".join(str(value) for value in identity[0][1:])
    token = _APPROVED_FILE_IDENTITY.set(proof)
    try:
        yield
    finally:
        _APPROVED_FILE_IDENTITY.reset(token)


def verify_local_file_available(path):
    """Reject PDFs whose cloud download is incomplete before scanning or opening.

    Query native macOS file metadata without reading bytes or triggering downloads.
    Non-PDF requests preserve their existing launch behavior.
    """
    path = Path(path)
    if path.suffix.lower() != ".pdf" or sys.platform != "darwin":
        return
    try:
        completed = subprocess.run(
            [str(NATIVE_LAUNCHER), "--check-local", str(path)],
            capture_output=True, timeout=10,
        )
    except (OSError, subprocess.SubprocessError) as error:
        raise RuntimeError(
            "The requested PDF is not available locally; opening was stopped."
        ) from error
    if completed.returncode != 0:
        raise RuntimeError(
            "The requested PDF is not available locally; opening was stopped."
        )

TARGET_APP_CONFIG = Path.home() / "Library/Application Support/Studio/allow-and-open/target-app.txt"
FALLBACK_APP_CONFIG = TARGET_APP_CONFIG.with_name("fallback-app.txt")


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
        raise RuntimeError(PDF_DEFAULT_BROWSER_UNAVAILABLE_MESSAGE) from error
    if not _valid_bundle_identifier(selected):
        raise RuntimeError(PDF_DEFAULT_BROWSER_UNAVAILABLE_MESSAGE)
    return selected


def _read_validated_application_setting(path, *, optional=False, allow_system_default=False):
    """Validate existing on-disk application settings without changing them.

    Reject symlinks, directories, non-ASCII input, oversized values and
    unexpected whitespace. Never silently replace a corrupt user choice.
    """
    try:
        descriptor = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    except FileNotFoundError:
        return None
    except OSError as error:
        raise RuntimeError("Cannot read the PDF application configuration; opening was stopped.") from error
    try:
        with os.fdopen(descriptor, "rb") as stream:
            if not stat.S_ISREG(os.fstat(stream.fileno()).st_mode):
                raise RuntimeError("The PDF application configuration must be a regular file; opening was stopped.")
            raw = stream.read(257)
    except OSError as error:
        raise RuntimeError("Cannot read the PDF application configuration; opening was stopped.") from error
    if not raw or len(raw) > 256:
        raise RuntimeError("Invalid PDF application configuration length; opening was stopped.")
    try:
        text = raw.decode("ascii")
    except UnicodeDecodeError as error:
        raise RuntimeError("Invalid PDF application configuration encoding; opening was stopped.") from error
    # Permit the installer/chooser's single trailing newline, not arbitrary
    # whitespace or extra lines that could mask invalid configuration.
    selected = text[:-1] if text.endswith("\n") else text
    if selected != selected.strip() or "\n" in selected or "\r" in selected or "\x00" in selected:
        raise RuntimeError("Invalid PDF application configuration whitespace; opening was stopped.")
    if allow_system_default and selected == PDF_SYSTEM_DEFAULT_BROWSER:
        return selected
    if not _valid_bundle_identifier(selected):
        raise RuntimeError("Invalid PDF application bundle identifier; opening was stopped.")
    return selected


def pdf_target_application():
    """Read the validated target or resolve the opt-in default browser once."""
    selected = _read_validated_application_setting(
        TARGET_APP_CONFIG, allow_system_default=True
    )
    if selected is None:
        return PDF_DEFAULT_BUNDLE_ID
    if selected == PDF_SYSTEM_DEFAULT_BROWSER:
        return _resolve_default_browser()
    return selected


def pdf_fallback_application(primary=None):
    """Read an optional validated fallback without changing user settings."""
    selected = _read_validated_application_setting(FALLBACK_APP_CONFIG, optional=True)
    return None if selected is None or selected == primary else selected


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
    identity = _APPROVED_FILE_IDENTITY.get()
    if identity is not None:
        command.extend(["--expected-identity", identity])
    if path.suffix.lower() == ".pdf":
        selected = target_app if target_app is not None else pdf_target_application()
        if selected == PDF_OPENER_BUNDLE_ID:
            raise RuntimeError("PDF Magic Opener cannot launch itself; opening was stopped.")
        command.extend(["--bundle-id", selected])
    subprocess.run([*command, str(path)], check=True, timeout=30)
