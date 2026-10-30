#!/usr/bin/env python3
"""Run relocated legacy tests with their original root-relative file contract.

Many historical suites resolve application sources from __file__. Materialize
untracked, short-lived copies at the repository root only while the selected
suite runs, rather than changing source imports or installed application paths.
"""
import json
from pathlib import Path
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parent.parent
MANIFEST = ROOT / "tests" / "manifest.json"


def run(arguments):
    if not arguments:
        raise ValueError("Expected tests/<category>/<file>.py [arguments], or --discover path")
    mapping = json.loads(MANIFEST.read_text(encoding="utf-8"))
    inverse = {new: old for old, new in mapping.items()}
    discover = arguments[0] == "--discover"
    selection = arguments[1] if discover else arguments[0]
    if selection not in inverse:
        raise ValueError(f"Unknown relocated test: {selection}")
    old = inverse[selection]
    command = (
        [sys.executable, "-m", "unittest", "discover", "-p", old, *arguments[2:]]
        if discover else [sys.executable, old, *arguments[1:]]
    )
    created = []
    try:
        # Never overwrite tracked, user-created, or concurrently staged paths.
        for original in mapping:
            destination = ROOT / original
            if destination.exists() or destination.is_symlink():
                raise RuntimeError(f"Refusing to replace existing test: {original}")
        for original, new in mapping.items():
            source = ROOT / new
            if not source.is_file() or source.is_symlink():
                raise RuntimeError(f"Missing or linked test source: {new}")
            destination = ROOT / original
            shutil.copy2(source, destination)
            created.append(destination)
        return subprocess.call(command, cwd=ROOT)
    finally:
        for destination in reversed(created):
            destination.unlink(missing_ok=True)


if __name__ == "__main__":
    try:
        raise SystemExit(run(sys.argv[1:]))
    except (OSError, ValueError, RuntimeError) as error:
        print(f"Relocated test runner: {error}", file=sys.stderr)
        raise SystemExit(2)
