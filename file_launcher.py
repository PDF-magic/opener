"""Launch files only after the caller's malware scan gate has accepted them.

Application selection belongs here, not in the ClamAV scan engine. Retain the
existing PDF-to-Brave behavior until user-configurable destinations are added.
"""

from pathlib import Path
import subprocess

PDF_DEFAULT_BUNDLE_ID = "com.brave.Browser"


def launch_clean_file(path):
    """Launch an already-approved file with the current destination policy."""
    path = Path(path)
    command = ["/usr/bin/open"]
    if path.suffix.lower() == ".pdf":
        command.extend(["-b", PDF_DEFAULT_BUNDLE_ID])
    subprocess.run([*command, str(path)], check=True)
