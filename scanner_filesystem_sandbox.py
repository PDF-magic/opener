"""macOS Seatbelt filesystem boundary for the installed ClamAV subprocess.

This applies only to the scanner child (including its version probe). The
parent still performs signature freshness, integrity, cache and launch checks.
"""

from contextlib import contextmanager
import os
from pathlib import Path
import stat
import sys
import tempfile


SANDBOX_EXEC = "/usr/bin/sandbox-exec"
BLOCK_MESSAGE = "Scanner filesystem isolation is unavailable; opening was stopped."

# ClamAV is installed in one of the fixed Homebrew/local prefixes. Its dynamic
# libraries must remain readable, but arbitrary user-home/private files must
# not. Metadata traversal is not permission to read document contents.
# The single target is a literal for files, a subtree for application bundles.
# Extracted temporary files live only in the private per-invocation scratch.
PROFILE = """(version 1)
(deny default)
(allow process-exec (literal (param "SCANNER")))
(allow sysctl-read)
(allow file-read-metadata (subpath "/"))
(allow file-read*
    (literal (param "SCANNER"))
    (literal "/")
    (subpath "/System")
    (subpath "/usr/bin")
    (subpath "/usr/lib")
    (subpath "/usr/share")
    (subpath "/bin")
    (subpath "/sbin")
    (subpath "/Library/Frameworks")
    (subpath "/Library/Developer/CommandLineTools")
    (subpath "/opt/homebrew/bin")
    (subpath "/opt/homebrew/lib")
    (subpath "/opt/homebrew/opt")
    (subpath "/opt/homebrew/Cellar")
    (subpath "/opt/homebrew/share")
    (subpath "/usr/local/bin")
    (subpath "/usr/local/lib")
    (subpath "/usr/local/opt")
    (subpath "/usr/local/Cellar")
    (subpath "/usr/local/share")
    (subpath "/usr/local/clamav")
    (subpath (param "DATABASE"))
    (literal (param "TARGET"))
    (subpath (param "BUNDLE"))
    (subpath (param "SCRATCH"))
    (literal "/dev/null")
    (literal "/dev/urandom"))
(allow file-write* (subpath (param "SCRATCH")))
"""


class ScannerFilesystemSandboxError(RuntimeError):
    """Never include a private scan path in failure diagnostics."""


def _executable(path, *, allow_symlink=False):
    if (type(path) is not str or not path.startswith("/") or
            "\x00" in path or "\r" in path or "\n" in path):
        return False
    try:
        resolved = os.path.realpath(path)
        info = os.stat(resolved, follow_symlinks=False)
        return (stat.S_ISREG(info.st_mode) and os.access(resolved, os.X_OK)
                and (allow_symlink or path == resolved))
    except OSError:
        return False


def _scan_paths(command, scan):
    if type(command) not in (tuple, list) or not command or not _executable(
            command[0], allow_symlink=True):
        raise ScannerFilesystemSandboxError(BLOCK_MESSAGE)
    if any(type(value) is not str or "\x00" in value for value in command):
        raise ScannerFilesystemSandboxError(BLOCK_MESSAGE)
    if scan:
        if (len(command) < 5 or command[-2] != "--" or
                not command[1].startswith("--database=")):
            raise ScannerFilesystemSandboxError(BLOCK_MESSAGE)
        database = Path(command[1].split("=", 1)[1])
        document = Path(command[-1])
        if (not database.is_absolute() or not document.is_absolute() or
                database.is_symlink() or not database.is_dir() or
                document.is_symlink() or
                not (document.is_file() or
                     (document.is_dir() and document.suffix.lower() == ".app"))):
            raise ScannerFilesystemSandboxError(BLOCK_MESSAGE)
        # Do not use a user-provided symlink to expand the sandbox allowlist.
        if str(document.resolve(strict=True)) != str(document):
            raise ScannerFilesystemSandboxError(BLOCK_MESSAGE)
        target = str(document) if document.is_file() else "/dev/null"
        bundle = str(document) if document.is_dir() else "/dev/null"
        return str(database.resolve(strict=True)), target, bundle
    if len(command) != 2 or command[1] != "--version":
        raise ScannerFilesystemSandboxError(BLOCK_MESSAGE)
    return "/dev/null", "/dev/null", "/dev/null"


@contextmanager
def confined_scanner(command, *, scan):
    """Return scanner argv and launch kwargs; never silently remove confinement.

    On non-macOS hosts retain the existing command for unit testing. Production
    is macOS, where unavailable Seatbelt support fails closed before spawn.
    """
    if sys.platform != "darwin":
        yield command, {}
        return
    if not _executable(SANDBOX_EXEC):
        raise ScannerFilesystemSandboxError(BLOCK_MESSAGE)
    try:
        database, target, bundle = _scan_paths(command, scan)
        scanner = os.path.realpath(command[0])
        # /tmp is an OS-managed scratch location, not a selected user document
        # or signature database. The directory is private and deleted on exit.
        with tempfile.TemporaryDirectory(prefix="opener-clamscan-", dir="/tmp") as temp:
            scratch = os.path.realpath(temp)
            if not os.path.isdir(scratch) or os.stat(scratch).st_mode & 0o077:
                raise ScannerFilesystemSandboxError(BLOCK_MESSAGE)
            argv = [
                SANDBOX_EXEC, "-p", PROFILE,
                "-D", "SCANNER=" + scanner,
                "-D", "DATABASE=" + database,
                "-D", "TARGET=" + target,
                "-D", "BUNDLE=" + bundle,
                "-D", "SCRATCH=" + scratch,
                *command,
            ]
            kwargs = {
                "cwd": "/",
                "env": {"PATH": "/usr/bin:/bin", "HOME": "/var/empty",
                        "TMPDIR": scratch, "TMP": scratch, "TEMP": scratch,
                        "LC_ALL": "C"},
                "close_fds": True,
            }
            yield argv, kwargs
    except (OSError, ValueError) as error:
        raise ScannerFilesystemSandboxError(BLOCK_MESSAGE) from None
