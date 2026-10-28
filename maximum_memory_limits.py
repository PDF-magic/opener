"""Enforce the memory ceiling for a *separate* Maximum PDF analysis worker.

This module is called only from the child created by opener-0306, before PDF
parsers are imported. It does not activate Maximum or affect Built-in scanning.
"""

import os
import resource
import signal
import sys

from protection_policy_definitions import PolicyControl
from protection_stage_resource_budgets import resource_budget_for_stage

MiB = 1024 * 1024
# The proposed isolated-behavior budget is a trusted, immutable policy input,
# never a value read from the PDF or a saved preference.
_POLICY_BUDGET = resource_budget_for_stage(PolicyControl.ISOLATED_BEHAVIOR_ANALYSIS)
WORKER_MEMORY_BYTES = _POLICY_BUDGET.memory_mib.maximum * MiB

# macOS may reserve several GiB of virtual address space for dyld and Python
# memory arenas. RLIMIT_DATA at the 1-GiB resident target can prevent even
# trusted parser imports; use a separate hard heap bound plus frequent RSS
# high-water checks in the *child*. The upper bound is not the RSS target.
MACOS_DATA_CEILING_BYTES = 8 * 1024 * MiB
MACOS_MONITOR_SECONDS = 0.05


class MaximumMemoryLimitError(RuntimeError):
    """No usable memory isolation: do not continue parsing."""


def _tighten_limit(kind: int, bytes_limit: int) -> None:
    if type(bytes_limit) is not int or bytes_limit <= 0:
        raise MaximumMemoryLimitError("Memory limit unavailable")
    soft, hard = resource.getrlimit(kind)
    # Never raise an inherited tighter hard or soft ceiling. RLIM_INFINITY can
    # be -1 or an unsigned platform-specific sentinel.
    ceiling = bytes_limit
    for existing in (soft, hard):
        if existing != resource.RLIM_INFINITY:
            ceiling = min(ceiling, existing)
    if ceiling <= 0:
        raise MaximumMemoryLimitError("Memory limit unavailable")
    resource.setrlimit(kind, (ceiling, ceiling))
    now_soft, now_hard = resource.getrlimit(kind)
    if now_soft > ceiling or now_hard > ceiling:
        raise MaximumMemoryLimitError("Memory limit unavailable")


def _macos_resident_bytes() -> int:
    usage = resource.getrusage(resource.RUSAGE_SELF)
    # macOS reports ru_maxrss as bytes, Linux reports KiB. This function is
    # macOS-only; its units are intentionally not platform-agnostic.
    value = usage.ru_maxrss
    if type(value) is not int or value < 0:
        raise MaximumMemoryLimitError("Memory usage unavailable")
    return value


def _macos_memory_alarm(_signum, _frame) -> None:
    # Signal delivery only happens in the child, not the GUI/ClamAV parent.
    if _macos_resident_bytes() > WORKER_MEMORY_BYTES:
        raise MaximumMemoryLimitError("Maximum worker memory limit exceeded")


def impose_maximum_worker_memory_limit() -> None:
    """Set OS ceilings before untrusted PDF inspection; fail closed on errors.

    Linux: hard RLIMIT_AS at the configured worker budget.
    macOS: hard RLIMIT_DATA safety cap plus periodic 1-GiB resident-memory
    high-water guard, since RLIMIT_AS at that value blocks macOS dyld imports.
    Monitoring is a best-effort RSS backstop, not a hard atomic RSS rlimit.
    Unsupported platforms fail closed. No unsandboxed/unlimited fallback.
    """
    if (type(WORKER_MEMORY_BYTES) is not int or
            not 0 < WORKER_MEMORY_BYTES <= 1024 * MiB):
        raise MaximumMemoryLimitError("Memory budget invalid")
    try:
        if sys.platform == "linux":
            _tighten_limit(resource.RLIMIT_AS, WORKER_MEMORY_BYTES)
        elif sys.platform == "darwin":
            _tighten_limit(resource.RLIMIT_DATA, MACOS_DATA_CEILING_BYTES)
            if (not hasattr(signal, "SIGALRM") or
                    not hasattr(signal, "ITIMER_REAL") or
                    not hasattr(signal, "setitimer")):
                raise MaximumMemoryLimitError("Memory monitoring unavailable")
            _macos_memory_alarm(0, None)
            signal.signal(signal.SIGALRM, _macos_memory_alarm)
            signal.setitimer(signal.ITIMER_REAL,
                             MACOS_MONITOR_SECONDS, MACOS_MONITOR_SECONDS)
        else:
            raise MaximumMemoryLimitError("Memory limits unavailable on this platform")
    except (OSError, ValueError, OverflowError) as exc:
        raise MaximumMemoryLimitError("Memory limit unavailable") from None
