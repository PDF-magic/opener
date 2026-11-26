#!/usr/bin/env python3
"""Find an available Homebrew command without executing it or changing the host."""

import os
from pathlib import Path
import sys

STANDARD_BREW_PATHS = (Path("/opt/homebrew/bin/brew"), Path("/usr/local/bin/brew"))


def detect_homebrew(known_paths=STANDARD_BREW_PATHS, search_path=None):
    """Return the first executable regular brew path, or None when unavailable."""
    if search_path is None:
        search_path = os.environ.get("PATH", "")

    # Check macOS's supported Homebrew prefixes even when Finder's PATH is sparse.
    candidates = list(known_paths)
    # Ignore relative and empty PATH entries; installers must not run ./brew.
    candidates.extend(
        Path(entry) / "brew" for entry in search_path.split(os.pathsep)
        if os.path.isabs(entry)
    )
    for candidate in candidates:
        try:
            if candidate.is_file() and os.access(candidate, os.X_OK):
                return str(candidate)
        except OSError:
            continue
    return None


def main():
    executable = detect_homebrew()
    if executable is None:
        print("Homebrew is unavailable; install Homebrew before installing ClamAV.", file=sys.stderr)
        return 1
    print(executable)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
