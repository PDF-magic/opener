"""Network-denied subprocess for a future Maximum PDF inspection worker.

This standalone launcher does not activate Maximum, replace the installed
ClamAV scanner, open documents, or modify user preferences. Calls require a
trusted executable and are rejected if macOS network isolation is unavailable.
"""

from dataclasses import dataclass
import os
import subprocess
import sys

SANDBOX_EXEC = "/usr/bin/sandbox-exec"
# Constant, non-user-controlled Seatbelt policy for the *child process*.
# Network access is denied for both incoming and outgoing operations, including
# loopback. The other process capabilities are deliberately unchanged here;
# file-system confinement and inspection orchestration are separate tasks.
NETWORK_DENY_PROFILE = "(version 1)\n(allow default)\n(deny network*)\n"
MAX_TIMEOUT_SECONDS = 600
MAX_ARGUMENTS = 64
MAX_ARGUMENT_BYTES = 8192
BLOCK_MESSAGE = "The Maximum analysis worker could not run without network access; opening was stopped."

# Do not inherit the host's proxy, cloud, credential, or runtime variables.
WORKER_ENV = {"PATH": "/usr/bin:/bin", "HOME": "/var/empty",
              "TMPDIR": "/tmp", "PYTHONDONTWRITEBYTECODE": "1"}


class MaximumNetworkIsolationError(RuntimeError):
    """A path-free, non-clean outcome for failed isolation or worker execution."""


@dataclass(frozen=True)
class OfflineWorkerCompletion:
    """Process completion evidence only; NEVER permission to open the PDF."""

    network_denied: bool = True
    authorizes_open: bool = False

    def __post_init__(self):
        if self.network_denied is not True or self.authorizes_open is not False:
            raise ValueError("Offline worker results cannot authorize opening")


def run_maximum_offline_worker(command: tuple[str, ...], *, timeout_seconds: int = 120):
    """Run trusted Maximum-only analysis as a network-denied child on macOS.

    The kernel-level sandbox is applied before the worker starts. No unisolated
    fallback is ever tried; output and diagnostics are discarded, including
    potentially malicious PDF data or private paths. The method returns only
    evidence of process completion, not a scan verdict.
    """
    if (type(command) is not tuple or not 1 <= len(command) <= MAX_ARGUMENTS or
            any(type(arg) is not str or not arg or "\x00" in arg or
                len(arg.encode("utf-8")) > MAX_ARGUMENT_BYTES for arg in command) or
            not os.path.isabs(command[0]) or
            type(timeout_seconds) is not int or
            not 1 <= timeout_seconds <= MAX_TIMEOUT_SECONDS):
        raise ValueError("Maximum worker needs a bounded, trusted absolute command")
    if (sys.platform != "darwin" or
            not os.path.isfile(SANDBOX_EXEC) or
            not os.access(SANDBOX_EXEC, os.X_OK)):
        raise MaximumNetworkIsolationError(BLOCK_MESSAGE)
    try:
        result = subprocess.run(
            [SANDBOX_EXEC, "-p", NETWORK_DENY_PROFILE, *command],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=timeout_seconds,
            check=False,
            close_fds=True,
            cwd="/",
            env=WORKER_ENV.copy(),
        )
    except (OSError, subprocess.SubprocessError):
        raise MaximumNetworkIsolationError(BLOCK_MESSAGE) from None
    if result.returncode != 0:
        raise MaximumNetworkIsolationError(BLOCK_MESSAGE)
    return OfflineWorkerCompletion()
