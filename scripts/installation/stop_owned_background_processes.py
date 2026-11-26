#!/usr/bin/env python3
"""Explicitly stop only verified PDF Magic Opener per-user processes on uninstall.

No process is signalled on inspection; --stop requires an interactive STOP.
The signature LaunchAgent is retired separately by uninstall_signature_launchagent.py.
Never match processes by basename alone, terminate shared ClamAV services, or
escalate to SIGKILL if graceful shutdown cannot be verified.
"""

import argparse
import ctypes
from dataclasses import dataclass
import os
from pathlib import Path
import plistlib
import signal
import stat
import subprocess
import sys
import time


class ProcessStopRefused(ValueError):
    """Unrecognized process identity or incomplete shutdown: do not uninstall."""


@dataclass(frozen=True)
class ProcessEntry:
    pid: int
    uid: int
    started: str
    command: str


def list_processes():
    result = subprocess.run(
        ["/bin/ps", "-axo", "pid=,uid=,lstart=,command=", "-ww"],
        capture_output=True, text=True, timeout=10, check=True,
    )
    records = []
    for line in result.stdout.splitlines():
        fields = line.strip().split(None, 7)
        if len(fields) != 8:
            raise ProcessStopRefused("Cannot reliably inspect running processes.")
        pid, uid, weekday, month, day, clock, year, command = fields
        if not pid.isdecimal() or not uid.isdecimal():
            raise ProcessStopRefused("Cannot reliably inspect process identities.")
        records.append(ProcessEntry(
            int(pid), int(uid), " ".join((weekday, month, day, clock, year)), command
        ))
    return records


def process_executable(pid):
    """Obtain the kernel-reported executable path, not an argv[0] claim."""
    library = ctypes.CDLL("/usr/lib/libproc.dylib")
    function = library.proc_pidpath
    function.argtypes = (ctypes.c_int, ctypes.c_void_p, ctypes.c_uint32)
    function.restype = ctypes.c_int
    buffer = ctypes.create_string_buffer(4096)
    if function(pid, buffer, len(buffer)) <= 0:
        return None  # Process exited or permission was denied; caller rechecks.
    return os.fsdecode(buffer.value)


def _safe_installed_file(home, candidate, uid):
    """Refuse symlinked/foreign/mutable shared paths rather than guessing ownership."""
    if candidate != home and home not in candidate.parents:
        raise ProcessStopRefused("Unexpected installed process path.")
    cursor = home
    parts = candidate.relative_to(home).parts
    for part in parts:
        cursor = cursor / part
        try:
            info = cursor.lstat()
        except OSError as error:
            raise ProcessStopRefused("Installed process identity cannot be verified.") from error
        if stat.S_ISLNK(info.st_mode) or info.st_uid != uid or info.st_mode & 0o022:
            raise ProcessStopRefused("Unsafe installed process path.")
    if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1:
        raise ProcessStopRefused("Installed process executable is not a regular owned file.")


def _script_invocation(command, script, interpreter):
    # ps displays the raw command line, with spaces in the absolute support
    # directory. Match a complete fixed script path including its boundary,
    # never a substring, process name, PID file, document path or arbitrary ID.
    launcher, separator, arguments = command.partition(" ")
    if not separator:
        return False
    name = Path(launcher).name
    if interpreter == "python":
        if name not in {"python3", "python3.11", "python3.12", "python3.13", "python3.14"}:
            return False
    elif name not in {"bash", "sh"}:
        return False
    return arguments == str(script) or arguments.startswith(str(script) + " ")


def _managed(entry, home, executable):
    if entry.pid <= 1 or entry.pid == os.getpid() or entry.uid != os.getuid():
        return False
    support = home / "Library/Application Support/Studio/allow-and-open"
    app = home / "Applications/PDF Magic Opener.app"
    app_binary = app / "Contents/MacOS/PDFOpener"
    host_binary = support / "pdf-magic-native-host"
    if executable in (str(app_binary), str(host_binary)):
        target = app_binary if executable == str(app_binary) else host_binary
        _safe_installed_file(home, target, entry.uid)
        if target == app_binary:
            info_path = app / "Contents/Info.plist"
            _safe_installed_file(home, info_path, entry.uid)
            try:
                with info_path.open("rb") as stream:
                    identity = plistlib.load(stream)
            except (OSError, ValueError, plistlib.InvalidFileException) as error:
                raise ProcessStopRefused("Application identity could not be verified.") from error
            if (identity.get("CFBundleIdentifier") != "local.studio.brave-pdf-opener"
                    or identity.get("CFBundleExecutable") != "PDFOpener"):
                raise ProcessStopRefused("Unrecognized PDF opener bundle.")
        return True

    # The installed scan entry point is a Python process. Its own cancellation
    # handler terminates its isolated ClamAV subprocess group when signalled.
    script = support / "scan-and-open.py"
    if _script_invocation(entry.command, script, "python"):
        if Path(executable or "").name not in {
            "python3", "python3.11", "python3.12", "python3.13", "python3.14"
        }:
            raise ProcessStopRefused("Unrecognized scan helper executable.")
        _safe_installed_file(home, script, entry.uid)
        return True

    # Managed shell entry points; updater traps SIGTERM and stops its own
    # FreshClam child. Do not directly signal freshclam, clamscan or browsers.
    if executable == "/bin/bash":
        for name in ("allow-and-open.sh", "update-malware-signatures.sh"):
            script = support / name
            if _script_invocation(entry.command, script, "shell"):
                _safe_installed_file(home, script, entry.uid)
                return True
    return False


def owned_processes(home, *, snapshot=list_processes, executable=process_executable):
    matches = []
    for entry in snapshot():
        if entry.uid != os.getuid() or entry.pid == os.getpid():
            continue
        path = executable(entry.pid)
        if path is None:
            # An exited process is not a candidate for signalling.
            continue
        if _managed(entry, home, path):
            matches.append((entry, path))
    return matches


def stop_owned_processes(home, *, stop=False, snapshot=list_processes,
                         executable=process_executable, send=os.kill,
                         sleep=time.sleep, attempts=10):
    """Inspect, or stop after revalidating each PID and waiting for full exit.

    The entry's start-time, command line, user and kernel executable must
    still match immediately before SIGTERM; a reused PID is never signalled.
    """
    home = Path(home)
    if sys.platform != "darwin" or os.geteuid() == 0 or not home.is_absolute():
        raise ProcessStopRefused("Requires a non-root macOS user session.")
    if home.is_symlink() or not home.is_dir() or home.stat().st_uid != os.getuid():
        raise ProcessStopRefused("Unrecognized installation home.")
    initial = owned_processes(home, snapshot=snapshot, executable=executable)
    if not stop:
        return f"{len(initial)} verified PDF Magic process(es); no changes made."
    for old, old_path in initial:
        # Re-inspect immediately before each signal; never trust a stale ps row.
        current = next((entry for entry in snapshot() if entry.pid == old.pid), None)
        if current is None:
            continue
        if current != old or executable(old.pid) != old_path or not _managed(
            current, home, old_path
        ):
            raise ProcessStopRefused("Process identity changed; stop refused.")
        try:
            send(old.pid, signal.SIGTERM)
        except ProcessLookupError:
            pass
        except OSError as error:
            raise ProcessStopRefused("Could not stop a verified PDF Magic process.") from error
    for _ in range(attempts):
        if not owned_processes(home, snapshot=snapshot, executable=executable):
            return "Verified PDF Magic processes stopped; other processes untouched."
        sleep(0.5)
    raise ProcessStopRefused(
        "PDF Magic processes are still active; do not remove their installed helpers."
    )


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--stop", action="store_true",
                        help="explicitly stop verified per-user PDF Magic processes")
    args = parser.parse_args(argv)
    if args.stop:
        try:
            answer = input("Type STOP to terminate verified PDF Magic processes: ")
        except (EOFError, KeyboardInterrupt):
            answer = ""
        if answer != "STOP":
            print("Process stop cancelled; nothing signalled.", file=sys.stderr)
            return 1
    try:
        print(stop_owned_processes(Path.home(), stop=args.stop))
    except (ProcessStopRefused, OSError, subprocess.SubprocessError) as error:
        print(f"Process stop refused: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
