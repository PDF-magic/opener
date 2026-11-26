#!/usr/bin/env python3
"""Install the trusted signature-update LaunchAgent without erasing safe user settings.

opener-0942: existing installations retain their schedule and logging choices.
The agent is never executed by this helper; the installer bootstraps it only
once the application and this migration have succeeded.
"""

import os
from pathlib import Path
import plistlib
import secrets
import stat
import sys

AGENT_NAME = "local.studio.pdf-malware-signatures.plist"
LABEL = "local.studio.pdf-malware-signatures"
ALLOWED_KEYS = frozenset({
    "Label", "ProgramArguments", "StartInterval", "StartCalendarInterval",
    "RunAtLoad", "Disabled", "ProcessType", "StandardOutPath", "StandardErrorPath",
})
CALENDAR_RANGES = {
    "Minute": (0, 59), "Hour": (0, 23), "Day": (1, 31),
    "Weekday": (0, 7), "Month": (1, 12),
}


def _calendar_valid(value):
    entries = value if isinstance(value, list) else [value]
    return bool(entries) and all(
        isinstance(entry, dict) and bool(entry)
        and all(
            key in CALENDAR_RANGES
            and type(number) is int
            and CALENDAR_RANGES[key][0] <= number <= CALENDAR_RANGES[key][1]
            for key, number in entry.items()
        ) for entry in entries
    )


def _regular_log(path, log_dir):
    if not isinstance(path, str) or not path or "\x00" in path:
        raise ValueError("Invalid update-agent log path")
    candidate = Path(path)
    if candidate.parent != log_dir or candidate.name in ("", ".", ".."):
        raise ValueError("Update-agent logs must remain in the application's log directory")
    try:
        info = candidate.lstat()
    except FileNotFoundError:
        return
    if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1 or info.st_uid != os.getuid():
        raise ValueError("Unsafe existing update-agent log file")


def _migrated(old, defaults, log_dir):
    if not isinstance(old, dict) or set(old) - ALLOWED_KEYS:
        raise ValueError("Unsupported existing update-agent configuration")
    if old.get("Label") != LABEL or old.get("ProgramArguments") != defaults["ProgramArguments"]:
        raise ValueError("Existing update agent has an unexpected identity or executable")
    if old.get("ProcessType", "Background") != "Background":
        raise ValueError("Unexpected update-agent process type")
    result = dict(defaults)
    for key in ("RunAtLoad", "Disabled"):
        if key in old:
            if type(old[key]) is not bool:
                raise ValueError("Invalid update-agent boolean setting")
            result[key] = old[key]
    if "StartInterval" in old:
        interval = old["StartInterval"]
        if type(interval) is not int or not 1 <= interval <= 31536000:
            raise ValueError("Invalid update-agent update interval")
        result["StartInterval"] = interval
    else:
        result.pop("StartInterval")
    if "StartCalendarInterval" in old:
        if not _calendar_valid(old["StartCalendarInterval"]):
            raise ValueError("Invalid update-agent calendar schedule")
        result["StartCalendarInterval"] = old["StartCalendarInterval"]
    if not ("StartInterval" in result or "StartCalendarInterval" in result
            or result.get("RunAtLoad") or result.get("Disabled")):
        raise ValueError("Existing update agent has no usable schedule")
    for key in ("StandardOutPath", "StandardErrorPath"):
        if key in old:
            _regular_log(old[key], log_dir)
            result[key] = old[key]
    return result


def migrate(home):
    home = Path(home)
    install_dir = home / "Library/Application Support/Studio/allow-and-open"
    log_dir = home / "Library/Logs/Studio"
    for directory in (log_dir,):
        info = directory.lstat()
        if not stat.S_ISDIR(info.st_mode) or info.st_uid != os.getuid() or info.st_mode & 0o022:
            raise ValueError("Unsafe update-agent log directory")
    defaults = {
        "Label": LABEL,
        "ProgramArguments": ["/bin/bash", str(install_dir / "update-malware-signatures.sh")],
        "StartInterval": 14400,
        "RunAtLoad": True,
        "ProcessType": "Background",
        "StandardOutPath": str(log_dir / "pdf-malware-signatures.log"),
        "StandardErrorPath": str(log_dir / "pdf-malware-signatures.error.log"),
    }
    for key in ("StandardOutPath", "StandardErrorPath"):
        _regular_log(defaults[key], log_dir)
    agent_dir = home / "Library/LaunchAgents"
    directory_fd = os.open(agent_dir, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    temporary = None
    try:
        parent = os.fstat(directory_fd)
        if (not stat.S_ISDIR(parent.st_mode) or parent.st_uid != os.getuid()
                or parent.st_mode & 0o022):
            raise ValueError("Unsafe update-agent directory")
        original = None
        identity = None
        try:
            existing_fd = os.open(AGENT_NAME, os.O_RDONLY | os.O_NOFOLLOW, dir_fd=directory_fd)
        except FileNotFoundError:
            pass
        else:
            with os.fdopen(existing_fd, "rb") as stream:
                identity = os.fstat(stream.fileno())
                if (not stat.S_ISREG(identity.st_mode) or identity.st_nlink != 1
                        or identity.st_uid != os.getuid() or identity.st_mode & 0o022
                        or identity.st_size > 65536):
                    raise ValueError("Unsafe existing update-agent file")
                content = stream.read(65537)
                if len(content) > 65536:
                    raise ValueError("Oversized update-agent file")
                original = plistlib.loads(content)
            current = os.stat(AGENT_NAME, dir_fd=directory_fd, follow_symlinks=False)
            if (current.st_dev, current.st_ino) != (identity.st_dev, identity.st_ino):
                raise ValueError("Update-agent configuration changed while reading")
        updated = defaults if original is None else _migrated(original, defaults, log_dir)
        if original == updated:
            return  # No rewrite or restart needed to preserve the settings.
        payload = plistlib.dumps(updated, sort_keys=True)
        temporary = f".{AGENT_NAME}.{secrets.token_hex(12)}.tmp"
        flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW
        temp_fd = os.open(temporary, flags, 0o600, dir_fd=directory_fd)
        with os.fdopen(temp_fd, "wb") as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
        try:
            current = os.stat(AGENT_NAME, dir_fd=directory_fd, follow_symlinks=False)
        except FileNotFoundError:
            current = None
        if (identity is None and current is not None) or (identity is not None and (
                current is None or (current.st_dev, current.st_ino) !=
                (identity.st_dev, identity.st_ino))):
            raise ValueError("Update-agent configuration changed during migration")
        os.replace(temporary, AGENT_NAME, src_dir_fd=directory_fd, dst_dir_fd=directory_fd)
        temporary = None
        os.fsync(directory_fd)
    finally:
        if temporary is not None:
            os.unlink(temporary, dir_fd=directory_fd)
        os.close(directory_fd)


if __name__ == "__main__":
    try:
        migrate(Path.home())
    except (OSError, ValueError, plistlib.InvalidFileException) as error:
        print(f"Update-agent configuration migration refused: {error}", file=sys.stderr)
        sys.exit(1)
