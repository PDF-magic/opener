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

    @property
    def reason_record(self) -> "ExceptionRejectionReason":
        """Fixed structured refusal reason; never derived from request content."""
        return EXCEPTION_REJECTION_REASON


UNSUPPORTED_EXCEPTION_MESSAGE = (
    "Protection exceptions are not supported; mandatory scanning remains required."
)


class ExceptionRejectionCode(str, Enum):
    MANDATORY_PROTECTION_NO_EXCEPTIONS = "mandatory_protection_no_exceptions"


@dataclass(frozen=True)
class ExceptionRejectionReason:
    """Immutable policy-level reason, never an approved exception or a request log."""

    code: ExceptionRejectionCode = ExceptionRejectionCode.MANDATORY_PROTECTION_NO_EXCEPTIONS
    explanation: str = UNSUPPORTED_EXCEPTION_MESSAGE
    disposition: ExceptionDisposition = ExceptionDisposition.UNSUPPORTED

    def __post_init__(self) -> None:
        if (self.code is not ExceptionRejectionCode.MANDATORY_PROTECTION_NO_EXCEPTIONS or
                type(self.explanation) is not str or
                self.explanation != UNSUPPORTED_EXCEPTION_MESSAGE or
                self.disposition is not ExceptionDisposition.UNSUPPORTED):
            raise ProtectionExceptionNotSupported(UNSUPPORTED_EXCEPTION_MESSAGE)

    def as_document(self) -> dict[str, object]:
        """Detached, path-free structured reason suitable for safe display."""
        return {
            "reason_code": self.code.value,
            "reason": self.explanation,
            "disposition": self.disposition.value,
            "exception_granted": False,
        }


EXCEPTION_REJECTION_REASON = ExceptionRejectionReason()


def record_exception_rejection_reason(_request: object = None) -> ExceptionRejectionReason:
    """Return the policy's fixed refusal reason without inspecting any request.

    No exception is granted or stored. Actual per-file exception records are
    inapplicable because the product does not support exceptions.
    """
    return EXCEPTION_REJECTION_REASON


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

    @property
    def rejection_reason(self) -> ExceptionRejectionReason:
        """Expose the fixed reason for the unsupported-exceptions policy."""
        return EXCEPTION_REJECTION_REASON

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
