"""Launch files only after the caller's malware scan gate has accepted them.

Application selection belongs here, not in the ClamAV scan engine. Retain the
existing PDF-to-Brave behavior until user-configurable destinations are added.
"""

from pathlib import Path
import subprocess
from target_application import PDF_DEFAULT_BUNDLE_ID, resolve_target_application


def intended_destination(path):
    """Describe current launch selection without changing user settings."""
    path = Path(path)
    if path.suffix.lower() == ".pdf":
        return PDF_DEFAULT_BUNDLE_ID
    if path.is_dir() and path.suffix.lower() == ".app":
        return path.name
    return "system-default"


def prepare_launch_command(path):
    """Verify an installed PDF target before quarantine is removed."""
    path = Path(path)
    command = ["/usr/bin/open"]
    if path.suffix.lower() == ".pdf":
        command.extend(["-a", resolve_target_application(PDF_DEFAULT_BUNDLE_ID)])
    return (*command, str(path))


def launch_clean_file(path, *, prepared_command=None):
    """Launch using the previously validated target, when provided."""
    command = prepared_command if prepared_command is not None else prepare_launch_command(path)
    subprocess.run(list(command), check=True)
