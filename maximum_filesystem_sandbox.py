"""Deny-by-default macOS filesystem confinement for a future Maximum worker.

This is the filesystem-permission boundary for opener-0307, not the worker
implementation (opener-0306), a PDF parser, or an opening decision. The
existing Built-in ClamAV path never calls this module.
"""

from dataclasses import dataclass
import os
import stat
import subprocess
import sys


SANDBOX_EXEC = "/usr/bin/sandbox-exec"
MAX_INPUT_BYTES = 16 * 1024 * 1024
MAX_ARGS = 32
MAX_ARG_LENGTH = 512
MAX_SECONDS = 600
BLOCK_MESSAGE = "Maximum analysis filesystem isolation is unavailable; opening was stopped."

# The untrusted document arrives on an inherited stdin pipe; never allow its
# pathname. Only system/runtime files and the single trusted executable may
# be read. There is NO file-write*, broad home, temp directory, or network rule.
# Child processes may not fork or execute an arbitrary program.
#
# WORKER is a sandbox parameter, not concatenated Scheme source, so file names
# cannot inject permissions by closing a quoted SBPL string.
SANDBOX_PROFILE = """(version 1)
(deny default)
(allow process-exec (literal (param "WORKER")))
(allow sysctl-read)
(allow file-read-metadata (subpath "/"))
(allow file-read*
    (literal (param "WORKER"))
    (subpath "/System")
    (subpath "/usr/bin")
    (subpath "/usr/lib")
    (subpath "/usr/share")
    (subpath "/bin")
    (subpath "/sbin")
    (subpath "/Library/Developer/CommandLineTools")
    (subpath "/Library/Frameworks")
    (literal "/dev/null")
    (literal "/dev/urandom"))
"""


class MaximumFilesystemSandboxError(RuntimeError):
    """Fail-closed, path-free sandbox setup, launch or timeout error."""


@dataclass(frozen=True)
class MaximumFilesystemWorkerExit:
    """A subprocess exit status is NEVER a PDF scan verdict."""

    return_code: int
    permits_open: bool = False

    def __post_init__(self):
        if type(self.return_code) is not int or self.permits_open is not False:
            raise ValueError("An isolated worker cannot authorize opening")


def _trusted_executable(path: str) -> bool:
    # Reject symlinks in ANY path component, nonregular or writable binaries.
    if (type(path) is not str or not path.startswith("/") or "\x00" in path or
            os.path.normpath(path) != path or os.path.realpath(path) != path):
        return False
    try:
        info = os.stat(path, follow_symlinks=False)
        return (stat.S_ISREG(info.st_mode) and
                not info.st_mode & (stat.S_IWGRP | stat.S_IWOTH) and
                info.st_uid in (0, os.geteuid()) and
                os.access(path, os.X_OK))
    except OSError:
        return False


def run_maximum_filesystem_confined_worker(
    executable: str,
    arguments: tuple[str, ...],
    pdf_bytes: bytes,
    *,
    timeout_seconds: int = 60,
) -> MaximumFilesystemWorkerExit:
    """Launch only a trusted worker under an enforced macOS Seatbelt profile.

    Pass PDF bytes over stdin, never by filesystem path. No unsandboxed
    fallback is permitted if macOS, the helper or sandbox setup is unavailable.
    This function does NOT spawn the future Maximum behavioral analyzer
    automatically or change any installed scan or launch behavior.
    """
    if (sys.platform != "darwin" or
            type(pdf_bytes) is not bytes or not pdf_bytes or
            len(pdf_bytes) > MAX_INPUT_BYTES or
            type(arguments) is not tuple or len(arguments) > MAX_ARGS or
            any(type(arg) is not str or len(arg) > MAX_ARG_LENGTH or
                "\x00" in arg for arg in arguments) or
            type(timeout_seconds) is not int or
            not 1 <= timeout_seconds <= MAX_SECONDS or
            not _trusted_executable(SANDBOX_EXEC) or
            not _trusted_executable(executable)):
        raise MaximumFilesystemSandboxError(BLOCK_MESSAGE)

    # Do not forward HOME, user PYTHONPATH, proxies or shell startup settings.
    # Avoid retained inherited FDs, a user-controlled cwd and output files.
    env = {"PATH": "/usr/bin:/bin", "HOME": "/var/empty", "LC_ALL": "C"}
    command = (
        SANDBOX_EXEC, "-p", SANDBOX_PROFILE, "-D", "WORKER=" + executable,
        executable, *arguments,
    )
    try:
        completed = subprocess.run(
            command, input=pdf_bytes, stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL, timeout=timeout_seconds,
            cwd="/", env=env, close_fds=True, check=False,
        )
    except (OSError, subprocess.SubprocessError):
        raise MaximumFilesystemSandboxError(BLOCK_MESSAGE) from None
    return MaximumFilesystemWorkerExit(completed.returncode)
