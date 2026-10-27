"""Explicit, fail-closed lifecycle states for an individual file request.

This module defines the lifecycle contract only. Existing scan/open behavior is
unchanged until request processing is wired to these transitions separately.
"""

from enum import Enum
from types import MappingProxyType


class FileState(str, Enum):
    """The seven stable, case-sensitive file lifecycle states."""

    QUEUED = "queued"
    SCANNING = "scanning"
    ANALYZING = "analyzing"
    BLOCKED = "blocked"
    READY = "ready"
    OPENING = "opening"
    COMPLETED = "completed"


# Every unsuccessful intermediate phase can be blocked. Only successful
# completion of the preceding phase can advance the normal path. BLOCKED and
# COMPLETED are terminal; retrying requires a new file request in QUEUED.
VALID_TRANSITIONS = MappingProxyType({
    FileState.QUEUED: frozenset({FileState.SCANNING, FileState.BLOCKED}),
    FileState.SCANNING: frozenset({FileState.ANALYZING, FileState.BLOCKED}),
    FileState.ANALYZING: frozenset({FileState.READY, FileState.BLOCKED}),
    FileState.BLOCKED: frozenset(),
    FileState.READY: frozenset({FileState.OPENING, FileState.BLOCKED}),
    FileState.OPENING: frozenset({FileState.COMPLETED, FileState.BLOCKED}),
    FileState.COMPLETED: frozenset(),
})


def can_transition(current: FileState, next_state: FileState) -> bool:
    """Return whether the two explicit lifecycle states can be adjacent."""
    return (isinstance(current, FileState)
            and isinstance(next_state, FileState)
            and next_state in VALID_TRANSITIONS[current])


def transition_state(current: FileState, next_state: FileState) -> FileState:
    """Return a valid new state; reject invalid or bypassed transitions."""
    if not can_transition(current, next_state):
        raise ValueError(f"Invalid file lifecycle transition: {current!r} -> {next_state!r}")
    return next_state
