"""Protection exception support decision for PDF Magic Opener (opener-0342).

Decision: NO protection exceptions. This read-only contract is not a scanner,
a settings switch or permission to open a file. The installed Built-in
ClamAV and fail-closed integrity/handoff gates remain authoritative.

A verified content-addressed clean-scan cache hit or a verified destination
fallback is not a protection exception: both retain the existing safety gates.
"""

from dataclasses import dataclass
from enum import Enum


class ExceptionDisposition(str, Enum):
    UNSUPPORTED = "unsupported"


class ProtectionExceptionNotSupported(ValueError):
    """Attempting to exempt any item from mandatory checks is prohibited."""


UNSUPPORTED_EXCEPTION_MESSAGE = (
    "Protection exceptions are not supported; mandatory scanning remains required."
)


@dataclass(frozen=True)
class ProtectionExceptionDecision:
    """Immutable all-level decision; never an executable opening authorization."""

    supported: bool = False
    disposition: ExceptionDisposition = ExceptionDisposition.UNSUPPORTED

    def __post_init__(self) -> None:
        if type(self.supported) is not bool or self.supported:
            raise ProtectionExceptionNotSupported(UNSUPPORTED_EXCEPTION_MESSAGE)
        if self.disposition is not ExceptionDisposition.UNSUPPORTED:
            raise ProtectionExceptionNotSupported(UNSUPPORTED_EXCEPTION_MESSAGE)

    def as_document(self) -> dict[str, object]:
        """Detached, non-secret policy descriptor for documentation and tests."""
        return {
            "supported": self.supported,
            "disposition": self.disposition.value,
            "scope": "all_files_sources_destinations_and_protection_levels",
        }


EXCEPTION_SUPPORT_DECISION = ProtectionExceptionDecision()


def request_protection_exception(_request: object = None) -> None:
    """Always reject; never interpret untrusted paths, settings or file contents."""
    raise ProtectionExceptionNotSupported(UNSUPPORTED_EXCEPTION_MESSAGE)
