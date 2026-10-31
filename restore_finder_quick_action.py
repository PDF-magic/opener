#!/usr/bin/env python3
"""Explicitly restore the Finder Quick Action saved before PDF Magic migration.

Inspection is the default. Restoration is opt-in, never part of installation,
and never replaces a user-customized or unrecognized current workflow.
"""

import argparse
import copy
import os
from pathlib import Path
import plistlib
import stat
import tempfile


FIXED_COMMAND = (
    'export PDF_MAGIC_REQUEST_ORIGIN=finder\n'
    'exec /bin/bash "$HOME/Library/Application Support/Studio/'
    'allow-and-open/allow-and-open.sh" "$@"\n'
)
WORKFLOW_RELATIVE = Path("Library/Services/Allow and Open.workflow/Contents/document.wflow")
MAX_WORKFLOW_SIZE = 16 * 1024 * 1024


class RestorationRefused(Exception):
    """A file is missing, unsafe, changed, or not a known managed workflow."""


def _read_regular(path: Path, *, optional: bool = False):
    try:
        before = path.lstat()
    except FileNotFoundError:
        if optional:
            return None
        raise RestorationRefused("The original Finder Quick Action backup is missing.")
    except OSError as error:
        raise RestorationRefused(f"Cannot inspect Finder action: {error.strerror}") from error

    if (not stat.S_ISREG(before.st_mode) or before.st_nlink != 1
            or before.st_size > MAX_WORKFLOW_SIZE):
        raise RestorationRefused("Finder action or backup is unsafe; no files changed.")
    try:
        fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
        with os.fdopen(fd, "rb") as stream:
            opened = os.fstat(stream.fileno())
            if not stat.S_ISREG(opened.st_mode) or opened.st_nlink != 1:
                raise RestorationRefused("Finder action changed while being inspected.")
            if (opened.st_dev, opened.st_ino) != (before.st_dev, before.st_ino):
                raise RestorationRefused("Finder action changed while being inspected.")
            data = stream.read(MAX_WORKFLOW_SIZE + 1)
            after = os.fstat(stream.fileno())
    except OSError as error:
        raise RestorationRefused(f"Cannot safely read Finder action: {error.strerror}") from error

    if (len(data) > MAX_WORKFLOW_SIZE or after.st_size != len(data)
            or after.st_mtime_ns != opened.st_mtime_ns):
        raise RestorationRefused("Finder action changed while being inspected.")
    return data, opened


def _validate_parent(home: Path):
    current = home
    for part in WORKFLOW_RELATIVE.parts[:-1]:
        current = current / part
        try:
            mode = current.lstat().st_mode
        except OSError as error:
            raise RestorationRefused("Finder Quick Action directory is missing or unreadable.") from error
        if not stat.S_ISDIR(mode):
            raise RestorationRefused("Unsafe Finder Quick Action directory; no files changed.")


def _parse_workflow(data: bytes):
    try:
        workflow = plistlib.loads(data)
    except (ValueError, TypeError, OverflowError, plistlib.InvalidFileException) as error:
        raise RestorationRefused("Invalid Finder Quick Action property list.") from error
    if not isinstance(workflow, dict) or not isinstance(workflow.get("actions"), list):
        raise RestorationRefused("Invalid Finder Quick Action structure.")
    return workflow


def _shell_parameters(workflow):
    actions = [
        entry["action"] for entry in workflow["actions"]
        if isinstance(entry, dict) and isinstance(entry.get("action"), dict)
        and entry["action"].get("BundleIdentifier") == "com.apple.RunShellScript"
    ]
    if len(actions) != 1 or not isinstance(actions[0].get("ActionParameters"), dict):
        raise RestorationRefused("Expected exactly one Finder Run Shell Script action.")
    return actions[0]["ActionParameters"]


def _check_restore(backup_data: bytes, current_data: bytes | None):
    original = _parse_workflow(backup_data)
    params = _shell_parameters(original)
    if not isinstance(params.get("COMMAND_STRING"), str):
        raise RestorationRefused("Invalid original Finder shell command.")

    if current_data is None:
        return False  # A removed workflow can be restored from its original backup.
    if backup_data == current_data:
        return True  # Already restored: preserve its inode and customizations.

    managed = _parse_workflow(current_data)
    managed_params = _shell_parameters(managed)
    if (managed_params.get("COMMAND_STRING") != FIXED_COMMAND
            or managed_params.get("inputMethod") != 1
            or managed_params.get("shell") != "/bin/bash"):
        raise RestorationRefused("Current Finder action is not the managed scan-gated version.")

    # Verify *all* other user action parameters/preferences are unchanged.
    # A customized workflow must never be silently replaced by older backup data.
    expected = copy.deepcopy(original)
    expected_params = _shell_parameters(expected)
    expected_params["COMMAND_STRING"] = FIXED_COMMAND
    expected_params["inputMethod"] = 1
    expected_params["shell"] = "/bin/bash"
    if managed != expected:
        raise RestorationRefused("Current Finder action has later customizations; no files changed.")
    return False


def restore_finder_action(home: Path, *, restore: bool = False):
    path = home / WORKFLOW_RELATIVE
    backup = path.with_name("document.wflow.before-brave")
    _validate_parent(home)
    saved = _read_regular(backup)
    current = _read_regular(path, optional=True)
    already_restored = _check_restore(saved[0], None if current is None else current[0])

    if already_restored:
        return "Original Finder Quick Action is already restored; no changes made."
    if not restore:
        return "Original Finder action can be restored; rerun with --restore to confirm."

    staged = None
    try:
        with tempfile.NamedTemporaryFile(
            dir=path.parent, prefix=".document.wflow.restore.", delete=False
        ) as stream:
            staged = Path(stream.name)
            stream.write(saved[0])
            stream.flush()
            os.fsync(stream.fileno())
        os.chmod(staged, stat.S_IMODE(current[1].st_mode if current else saved[1].st_mode))
        _validate_parent(home)
        latest_backup = _read_regular(backup)
        if ((latest_backup[1].st_dev, latest_backup[1].st_ino) !=
                (saved[1].st_dev, saved[1].st_ino) or latest_backup[0] != saved[0]):
            raise RestorationRefused("Finder action backup changed; no files changed.")

        latest = _read_regular(path, optional=True)
        if current is None:
            if latest is not None:
                raise RestorationRefused("A new Finder action appeared; no files changed.")
            # Atomic create-if-absent: never overwrite another concurrently created action.
            os.link(staged, path)
        else:
            if (latest is None or latest[0] != current[0]
                    or (latest[1].st_dev, latest[1].st_ino) !=
                    (current[1].st_dev, current[1].st_ino)):
                raise RestorationRefused("Current Finder action changed; no files changed.")
            os.replace(staged, path)
        return "Original Finder Quick Action restored; saved backup retained."
    except FileExistsError as error:
        raise RestorationRefused("A new Finder action appeared; no files changed.") from error
    finally:
        if staged is not None:
            staged.unlink(missing_ok=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--restore", action="store_true", help="Explicitly restore the backed-up action")
    parser.add_argument("--home", type=Path, default=Path.home(), help=argparse.SUPPRESS)
    args = parser.parse_args()
    try:
        result = restore_finder_action(args.home, restore=args.restore)
    except (RestorationRefused, OSError) as error:
        parser.exit(1, f"Restoration refused: {error}\n")
    print(result)
    if args.restore:
        print("Note: the original Finder action may not use PDF Magic's malware scan gate.")


if __name__ == "__main__":
    main()
