#!/usr/bin/env python3
"""Read-only identification of the existing, project-owned FreshClam LaunchAgent.

This only inspects a fixed per-user path. It does not talk to launchctl,
create an agent, modify user settings, or run a signature update.
"""

from contextlib import ExitStack
import os
from pathlib import Path
import plistlib
import stat
import sys

AGENT_LABEL = "local.studio.pdf-malware-signatures"
AGENT_FILENAME = AGENT_LABEL + ".plist"
MAX_PLIST_BYTES = 65536


class UnrecognizedSignatureUpdateAgent(ValueError):
    """The expected agent path exists but is unsafe or not ours."""


def detect_existing_signature_update_agent(home):
    """Return True for our installed agent, False if absent; reject ambiguity.

    Match identity and executable invocation, not optional scheduling fields:
    users may have customized the update interval or log destinations.
    Parent directories and the plist must not be symlinks.
    """
    home = Path(home)
    if not home.is_absolute():
        raise UnrecognizedSignatureUpdateAgent("Home path must be absolute")

    directory_flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW
    file_flags = os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK
    try:
        with ExitStack() as opened:
            descriptor = os.open(home, directory_flags)
            opened.callback(os.close, descriptor)
            for component in ("Library", "LaunchAgents"):
                try:
                    descriptor = os.open(component, directory_flags, dir_fd=descriptor)
                except FileNotFoundError:
                    return False
                opened.callback(os.close, descriptor)
            try:
                agent_fd = os.open(AGENT_FILENAME, file_flags, dir_fd=descriptor)
            except FileNotFoundError:
                return False
            opened.callback(os.close, agent_fd)
            details = os.fstat(agent_fd)
            if not stat.S_ISREG(details.st_mode) or details.st_size > MAX_PLIST_BYTES:
                raise UnrecognizedSignatureUpdateAgent("Unexpected LaunchAgent file type or size")
            contents = os.read(agent_fd, MAX_PLIST_BYTES + 1)
            if len(contents) > MAX_PLIST_BYTES:
                raise UnrecognizedSignatureUpdateAgent("LaunchAgent plist exceeds size limit")
            properties = plistlib.loads(contents)
    except (OSError, plistlib.InvalidFileException, ValueError, TypeError) as error:
        raise UnrecognizedSignatureUpdateAgent("Cannot safely identify signature-update LaunchAgent") from error

    expected_arguments = [
        "/bin/bash",
        str(home / "Library/Application Support/Studio/allow-and-open/update-malware-signatures.sh"),
    ]
    if (not isinstance(properties, dict)
            or properties.get("Label") != AGENT_LABEL
            or properties.get("ProgramArguments") != expected_arguments):
        raise UnrecognizedSignatureUpdateAgent("Existing LaunchAgent does not match the updater identity")
    return True


def main():
    try:
        found = detect_existing_signature_update_agent(Path.home())
    except UnrecognizedSignatureUpdateAgent as error:
        print(str(error), file=sys.stderr)
        return 1
    print("existing" if found else "absent")
    return 0


if __name__ == "__main__":
    sys.exit(main())
