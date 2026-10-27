"""Resolve an installed macOS launch target before changing file quarantine."""

import json
from pathlib import Path
import subprocess

RESOLVER = Path.home() / "Library/Application Support/Studio/allow-and-open/resolve-target-app"
PDF_DEFAULT_BUNDLE_ID = "com.brave.Browser"


def resolve_target_application(bundle_identifier, *, resolver=RESOLVER):
    """Return a verified app path or fail closed; never accept a guessed location."""
    if not isinstance(bundle_identifier, str) or not bundle_identifier:
        raise RuntimeError("The target application is unavailable; opening was stopped.")
    try:
        completed = subprocess.run(
            [str(resolver), bundle_identifier], capture_output=True,
            text=True, check=True, timeout=10,
        )
        payload = json.loads(completed.stdout)
        app = payload["path"]
        if not isinstance(app, str) or not app or not Path(app).is_absolute():
            raise ValueError("Invalid resolved application path")
        target = Path(app)
        if target.suffix.lower() != ".app" or not target.is_dir():
            raise ValueError("Resolved application does not exist")
    except (OSError, subprocess.SubprocessError, ValueError, KeyError, TypeError) as error:
        raise RuntimeError(
            "The target application is unavailable; opening was stopped."
        ) from error
    return str(target)
