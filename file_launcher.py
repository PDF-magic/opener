"""Launch files only after the caller's malware scan gate has accepted them.

Application selection belongs here, not in the ClamAV scan engine. Retain the
existing PDF-to-Brave behavior until user-configurable destinations are added.
"""

from pathlib import Path
import subprocess

PDF_DEFAULT_BUNDLE_ID = "com.brave.Browser"
PDF_TARGET_VERIFIER = Path(__file__).with_name("verify-pdf-target")


def verify_launch_target(path):
    """Fail closed unless macOS recognizes the selected app as a PDF handler."""
    if Path(path).suffix.lower() != ".pdf":
        return
    try:
        result = subprocess.run(
            [str(PDF_TARGET_VERIFIER), intended_destination(path)],
            capture_output=True, timeout=10,
        )
    except (OSError, subprocess.SubprocessError) as error:
        raise RuntimeError("PDF application support could not be verified; opening was stopped.") from error
    if result.returncode != 0:
        raise RuntimeError("The selected application is not registered to open PDFs; opening was stopped.")



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
    command = ["/usr/bin/open"]
    if path.suffix.lower() == ".pdf":
        command.extend(["-b", PDF_DEFAULT_BUNDLE_ID])
    subprocess.run([*command, str(path)], check=True)
