#!/usr/bin/env python3
"""Explicitly choose and save a verified PDF application without opening a PDF.

The native picker validates the exact installed .app; the independent existing
PDF verifier checks launch eligibility again before a preference is saved.
"""
import argparse
import os
from pathlib import Path
import re
import stat
import subprocess
import sys
import uuid

PREFERENCE = Path.home() / "Library/Application Support/Studio/allow-and-open/target-app.txt"
NATIVE_PICKER = Path(__file__).with_name("select-custom-pdf-application")
PDF_VERIFIER = Path(__file__).with_name("verify-pdf-target")
BUNDLE_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9.-]{1,254}\Z")


def valid_bundle_id(value):
    return (isinstance(value, str) and BUNDLE_ID.fullmatch(value) is not None
            and "." in value and ".." not in value
            and value != "local.studio.brave-pdf-opener")


def persist_preference(identifier, destination):
    """Atomically replace only the exact regular preference file, never a link."""
    if not valid_bundle_id(identifier):
        raise ValueError("Invalid application bundle identifier.")
    destination = Path(destination)
    directory = destination.parent
    directory_fd = os.open(directory, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    temporary = ".target-app-" + uuid.uuid4().hex + ".tmp"
    try:
        try:
            previous = os.stat(destination.name, dir_fd=directory_fd, follow_symlinks=False)
        except FileNotFoundError:
            pass
        else:
            if not stat.S_ISREG(previous.st_mode):
                raise RuntimeError("The existing application setting is not a regular file.")
        # Avoid following symbolic links, and never write the preference in place.
        fd = os.open(temporary,
                     os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
                     0o600, dir_fd=directory_fd)
        try:
            with os.fdopen(fd, "wb") as stream:
                stream.write((identifier + "\n").encode("ascii"))
                stream.flush()
                os.fsync(stream.fileno())
        except BaseException:
            # fdopen owns fd, even when writing raises.
            raise
        os.replace(temporary, destination.name,
                   src_dir_fd=directory_fd, dst_dir_fd=directory_fd)
        os.fsync(directory_fd)
    finally:
        try:
            os.unlink(temporary, dir_fd=directory_fd)
        except FileNotFoundError:
            pass
        os.close(directory_fd)


def choose_and_save(application=None, destination=PREFERENCE):
    if application is not None:
        app = Path(application)
        if not app.is_absolute() or app.suffix.lower() != ".app":
            raise ValueError("Choose an absolute .app bundle path.")
    args = [str(NATIVE_PICKER)]
    if application is not None:
        args += ["--application", str(application)]
    try:
        selection = subprocess.run(args, capture_output=True, check=False,
                                   timeout=30 if application is not None else None)
    except (OSError, subprocess.SubprocessError) as error:
        raise RuntimeError("The macOS application chooser could not run.") from error
    if selection.returncode != 0:
        raise RuntimeError("Selection cancelled or the selected application is not eligible.")
    try:
        identifier = selection.stdout.decode("ascii")
    except UnicodeDecodeError as error:
        raise RuntimeError("The selected application's identity is invalid.") from error
    if not identifier.endswith("\n") or identifier.count("\n") != 1:
        raise RuntimeError("The application chooser returned an invalid identity.")
    identifier = identifier[:-1]
    if not valid_bundle_id(identifier):
        raise RuntimeError("The application chooser returned an invalid identity.")
    try:
        verified = subprocess.run(
            [str(PDF_VERIFIER), identifier], capture_output=True,
            check=False, timeout=10
        )
    except (OSError, subprocess.SubprocessError) as error:
        raise RuntimeError("PDF capability verification was unavailable.") from error
    if verified.returncode != 0:
        raise RuntimeError("The selected application cannot be verified to open PDFs.")
    persist_preference(identifier, destination)
    return identifier


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--application", help="Absolute path to a selected macOS .app bundle")
    args = parser.parse_args(argv)
    try:
        identifier = choose_and_save(args.application)
    except (ValueError, RuntimeError, OSError) as error:
        print(str(error), file=sys.stderr)
        return 1
    print("Saved PDF application: " + identifier)
    return 0


if __name__ == "__main__":
    sys.exit(main())
