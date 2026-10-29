"""Kernel-enforced network denial for optional Maximum-only worker processes.

These helpers do not activate Maximum, replace the installed ClamAV scanner,
open documents, or modify user preferences. Network isolation fails closed
when the operating-system enforcement mechanism is unavailable.
"""

from dataclasses import dataclass
import ctypes
import errno
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



LINUX_NETWORK_SYSCALLS = (
    "socket", "socketpair", "connect", "bind", "listen", "accept", "accept4",
    "getsockname", "getpeername", "sendto", "recvfrom", "sendmsg", "recvmsg",
    "shutdown", "setsockopt", "getsockopt", "recvmmsg", "sendmmsg",
    "io_uring_setup", "io_uring_enter", "io_uring_register", "socketcall",
)
LINUX_REQUIRED_NETWORK_SYSCALLS = frozenset((
    "socket", "socketpair", "connect", "bind", "listen", "accept", "accept4",
    "getsockname", "getpeername", "sendto", "recvfrom", "sendmsg", "recvmsg",
    "shutdown", "setsockopt", "getsockopt", "recvmmsg", "sendmmsg",
))
SCMP_ACT_ALLOW = 0x7FFF0000
SCMP_ACT_ERRNO = 0x00050000
PR_SET_NO_NEW_PRIVS = 38


def apply_linux_network_denial() -> None:
    """Install a process-wide seccomp filter before the renderer reads a PDF.

    Deny socket creation and all ordinary socket I/O operations, plus io_uring
    entry points that could otherwise submit network operations. The filter is
    inherited by child processes and threads. No permissive fallback exists.
    """
    if sys.platform != "linux":
        raise MaximumNetworkIsolationError(BLOCK_MESSAGE)

    library = None
    context = None
    try:
        # Require the system runtime library; do not shell out to discover it.
        library = ctypes.CDLL("libseccomp.so.2", use_errno=True)
        library.seccomp_init.argtypes = [ctypes.c_uint32]
        library.seccomp_init.restype = ctypes.c_void_p
        library.seccomp_rule_add.argtypes = [
            ctypes.c_void_p, ctypes.c_uint32, ctypes.c_int, ctypes.c_uint,
        ]
        library.seccomp_rule_add.restype = ctypes.c_int
        library.seccomp_syscall_resolve_name.argtypes = [ctypes.c_char_p]
        library.seccomp_syscall_resolve_name.restype = ctypes.c_int
        library.seccomp_load.argtypes = [ctypes.c_void_p]
        library.seccomp_load.restype = ctypes.c_int
        library.seccomp_release.argtypes = [ctypes.c_void_p]
        library.seccomp_release.restype = None

        context = library.seccomp_init(SCMP_ACT_ALLOW)
        if not context:
            raise RuntimeError

        resolved_required = set()
        denied_action = SCMP_ACT_ERRNO | errno.EPERM
        for name in LINUX_NETWORK_SYSCALLS:
            number = library.seccomp_syscall_resolve_name(name.encode("ascii"))
            if number < 0:
                if name in LINUX_REQUIRED_NETWORK_SYSCALLS:
                    raise RuntimeError
                continue
            if library.seccomp_rule_add(context, denied_action, number, 0) < 0:
                raise RuntimeError
            if name in LINUX_REQUIRED_NETWORK_SYSCALLS:
                resolved_required.add(name)
        if resolved_required != LINUX_REQUIRED_NETWORK_SYSCALLS:
            raise RuntimeError

        libc = ctypes.CDLL(None, use_errno=True)
        libc.prctl.argtypes = [
            ctypes.c_int, ctypes.c_ulong, ctypes.c_ulong,
            ctypes.c_ulong, ctypes.c_ulong,
        ]
        libc.prctl.restype = ctypes.c_int
        if libc.prctl(PR_SET_NO_NEW_PRIVS, 1, 0, 0, 0) != 0:
            raise RuntimeError
        if library.seccomp_load(context) < 0:
            raise RuntimeError
    except Exception:
        raise MaximumNetworkIsolationError(BLOCK_MESSAGE) from None
    finally:
        if context and library is not None:
            try:
                library.seccomp_release(context)
            except Exception:
                pass


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
