#!/usr/bin/env python3
"""Explicitly retire only PDF Magic Opener's verified per-user FreshClam LaunchAgent.

Inspection is read-only. --remove requires a terminal confirmation. It stops the
exact registered service before unlinking the exact installed plist, preserving
the complete original bytes in an exclusive same-directory recovery copy.
Other LaunchAgents, scanner signatures, and user settings are never removed.
"""

import argparse
from contextlib import ExitStack
import os
from pathlib import Path
import plistlib
import stat
import subprocess
import sys

from signature_update_launchagent import (
    AGENT_FILENAME, AGENT_LABEL, MAX_PLIST_BYTES,
    UnrecognizedSignatureUpdateAgent, detect_existing_signature_update_agent,
)

BACKUP_FILENAME = AGENT_FILENAME + ".before-uninstall"
_NOT_FOUND = ("could not find service", "service not found")


class AgentRemovalRefused(ValueError):
    """Do not delete anything unless service and exact file ownership are certain."""


def _run_launchctl(args):
    return subprocess.run(args, capture_output=True, text=True, timeout=10, check=False)


def _launchctl_loaded(run, uid):
    service = f"gui/{uid}/{AGENT_LABEL}"
    result = run(["/bin/launchctl", "print", service])
    if result.returncode == 0:
        return True
    diagnostic = (result.stderr or "").casefold()
    if any(message in diagnostic for message in _NOT_FOUND):
        return False
    raise AgentRemovalRefused("Cannot verify the signature-update service state.")


def _open_agents(home, opened):
    flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW
    descriptor = os.open(home, flags)
    opened.callback(os.close, descriptor)
    for component in ("Library", "LaunchAgents"):
        try:
            descriptor = os.open(component, flags, dir_fd=descriptor)
        except FileNotFoundError:
            return None
        opened.callback(os.close, descriptor)
    return descriptor


def _read_managed(dirfd, home):
    try:
        fd = os.open(AGENT_FILENAME, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK,
                     dir_fd=dirfd)
    except FileNotFoundError:
        return None
    with os.fdopen(fd, "rb") as stream:
        before = os.fstat(stream.fileno())
        if (not stat.S_ISREG(before.st_mode) or before.st_nlink != 1
                or before.st_uid != os.getuid() or before.st_mode & 0o022
                or not 0 < before.st_size <= MAX_PLIST_BYTES):
            raise AgentRemovalRefused("Unrecognized or unsafe LaunchAgent file; nothing removed.")
        content = stream.read(MAX_PLIST_BYTES + 1)
        after = os.fstat(stream.fileno())
        if (len(content) != before.st_size or after.st_size != before.st_size
                or after.st_mtime_ns != before.st_mtime_ns
                or (after.st_dev, after.st_ino) != (before.st_dev, before.st_ino)):
            raise AgentRemovalRefused("LaunchAgent changed during inspection.")
    try:
        info = plistlib.loads(content)
    except (ValueError, TypeError, OverflowError, plistlib.InvalidFileException) as error:
        raise AgentRemovalRefused("Unrecognized LaunchAgent plist; nothing removed.") from error
    expected = ["/bin/bash", str(home / "Library/Application Support/Studio/"
                                  "allow-and-open/update-malware-signatures.sh")]
    if (not isinstance(info, dict) or info.get("Label") != AGENT_LABEL
            or info.get("ProgramArguments") != expected):
        raise AgentRemovalRefused("LaunchAgent does not match PDF Magic's updater.")
    return content, before


def _same_record(a, b):
    return (a[0] == b[0] and
            (a[1].st_dev, a[1].st_ino, a[1].st_mtime_ns, a[1].st_size) ==
            (b[1].st_dev, b[1].st_ino, b[1].st_mtime_ns, b[1].st_size))


def _verify_directory(home, original):
    # A swapped directory would make launchctl and dirfd address different files.
    with ExitStack() as opened:
        fresh = _open_agents(home, opened)
        if fresh is None:
            raise AgentRemovalRefused("LaunchAgents directory changed during removal.")
        old, new = os.fstat(original), os.fstat(fresh)
        if (old.st_dev, old.st_ino) != (new.st_dev, new.st_ino):
            raise AgentRemovalRefused("LaunchAgents directory was replaced.")


def remove_signature_launchagent(home, *, remove=False, run=_run_launchctl):
    """Inspect or explicitly retire the known agent; suitable for synthetic CI homes.

    The run callback receives exact launchctl argv and returns CompletedProcess.
    It must never be invoked by an installer, scanner, or automatic startup hook.
    """
    home = Path(home)
    if not home.is_absolute():
        raise AgentRemovalRefused("Home directory must be absolute.")
    if os.geteuid() == 0:
        raise AgentRemovalRefused("Do not run LaunchAgent removal as root.")
    try:
        # Reuse the installer's identity validation rather than creating a
        # second independently permissive definition of a managed agent.
        known = detect_existing_signature_update_agent(home)
        with ExitStack() as opened:
            directory = _open_agents(home, opened)
            original = _read_managed(directory, home) if directory is not None else None
            if known != (original is not None):
                raise AgentRemovalRefused("LaunchAgent changed during inspection.")
            loaded = _launchctl_loaded(run, os.getuid())
            if not known:
                if loaded:
                    raise AgentRemovalRefused("Updater still loaded despite missing plist.")
                return "PDF Magic LaunchAgent absent; no changes made."
            if not remove:
                return ("PDF Magic LaunchAgent verified (" +
                        ("loaded" if loaded else "not loaded") +
                        "); rerun with --remove for explicit retirement.")
            if directory is None:
                raise AgentRemovalRefused("LaunchAgent directory is unavailable.")
            _verify_directory(home, directory)
            # Never overwrite an existing archival copy. This preserves a
            # user's custom calendar interval, Disabled flag and log settings.
            try:
                os.stat(BACKUP_FILENAME, dir_fd=directory, follow_symlinks=False)
            except FileNotFoundError:
                pass
            else:
                raise AgentRemovalRefused("Recovery copy already exists; nothing removed.")

            if loaded:
                result = run(["/bin/launchctl", "bootout", f"gui/{os.getuid()}",
                              str(home / "Library/LaunchAgents" / AGENT_FILENAME)])
                if result.returncode != 0:
                    raise AgentRemovalRefused("Cannot stop verified update agent; plist retained.")
            if _launchctl_loaded(run, os.getuid()):
                raise AgentRemovalRefused("Updater remains loaded; plist retained.")

            _verify_directory(home, directory)
            current = _read_managed(directory, home)
            if current is None or not _same_record(original, current):
                raise AgentRemovalRefused("LaunchAgent changed after service stop; plist retained.")
            os.link(AGENT_FILENAME, BACKUP_FILENAME, src_dir_fd=directory,
                    dst_dir_fd=directory, follow_symlinks=False)
            # A hard link preserves exactly the same file bytes and permissions
            # without overwriting an existing backup or exposing its contents.
            try:
                newest = _read_managed(directory, home)
                backup = os.stat(BACKUP_FILENAME, dir_fd=directory, follow_symlinks=False)
                if (newest is None or not _same_record(original, newest)
                        or (backup.st_dev, backup.st_ino) !=
                        (original[1].st_dev, original[1].st_ino)):
                    raise AgentRemovalRefused("LaunchAgent changed; recovery copy retained.")
                if _launchctl_loaded(run, os.getuid()):
                    raise AgentRemovalRefused("Updater restarted; recovery copy retained.")
                os.unlink(AGENT_FILENAME, dir_fd=directory)
            except Exception:
                # The safe backup remains available to restore manually.
                raise
            return "PDF Magic LaunchAgent removed; original plist archived for recovery."
    except (UnrecognizedSignatureUpdateAgent, OSError, subprocess.SubprocessError,
            ValueError) as error:
        raise AgentRemovalRefused(str(error) or "Cannot safely retire LaunchAgent.") from error


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--remove", action="store_true",
                        help="Stop and archive only the verified PDF Magic update agent")
    args = parser.parse_args(argv)
    if sys.platform != "darwin":
        parser.exit(1, "This helper runs only on macOS.\n")
    if args.remove:
        if not sys.stdin.isatty():
            parser.exit(1, "Interactive terminal confirmation is required.\n")
        try:
            answer = input("Type REMOVE to retire PDF Magic's LaunchAgent: ")
        except EOFError:
            parser.exit(1, "Confirmation not received.\n")
        if answer != "REMOVE":
            parser.exit(1, "No changes made.\n")
    try:
        print(remove_signature_launchagent(Path.home(), remove=args.remove))
    except AgentRemovalRefused as error:
        parser.exit(1, f"Removal refused: {error}\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
