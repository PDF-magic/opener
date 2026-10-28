"""Fail-closed responses for scanner failures (opener-0255).

This describes how a *trusted* scanner failure should be handled. It does not
infer outcomes from untrusted stderr, replace ClamAV, launch files, or change
the installed scanner gate. The broader terminal-status matrix is handled by
opener-0253; these categories distinguish concrete scanner failure modes.
"""

from dataclasses import dataclass
from enum import Enum
from types import MappingProxyType

from scan_results import ScanResultStatus


class ScannerFailureKind(str, Enum):
    INITIALIZATION_FAILED = "initializationFailed"
    PROCESS_FAILED = "processFailed"
    INCOMPLETE_RESULT = "incompleteResult"
    TIMED_OUT = "timedOut"


# Fixed, path-free messages. Never include raw scanner stderr or file names.
INITIALIZATION_MESSAGE = "The scanner could not start; opening was stopped."
PROCESS_MESSAGE = "The malware scan could not finish; opening was stopped."
INCOMPLETE_MESSAGE = (
    "The malware scan did not confirm a complete scan; opening was stopped."
)
TIMEOUT_MESSAGE = "The malware scan timed out; opening was stopped."
UNKNOWN_MESSAGE = (
    "The scanner failed or its result could not be verified; opening was stopped."
)

_APPROVED_MESSAGES = frozenset({
    INITIALIZATION_MESSAGE,
    PROCESS_MESSAGE,
    INCOMPLETE_MESSAGE,
    TIMEOUT_MESSAGE,
    UNKNOWN_MESSAGE,
})
_FAILURE_STATUSES = frozenset({
    ScanResultStatus.scanFailed,
    ScanResultStatus.scanTimedOut,
    ScanResultStatus.incompleteScan,
})


@dataclass(frozen=True)
class ScannerFailureResponse:
    """Terminal denial guidance, not an authorization to modify the scan gate."""

    scan_status: ScanResultStatus
    user_message: str
    show_failure_alert: bool = True
    preserve_quarantine: bool = True
    allow_clean_cache: bool = False
    allow_open: bool = False
    allow_fallback: bool = False
    allow_override: bool = False
    retry_automatically: bool = False

    def __post_init__(self):
        if (not isinstance(self.scan_status, ScanResultStatus)
                or self.scan_status not in _FAILURE_STATUSES):
            raise ValueError("Scanner failure cannot produce a clean scan result.")
        if self.user_message not in _APPROVED_MESSAGES:
            raise ValueError("Scanner failures require fixed, path-free messages.")
        if (self.show_failure_alert is not True
                or self.preserve_quarantine is not True
                or self.allow_clean_cache is not False
                or self.allow_open is not False
                or self.allow_fallback is not False
                or self.allow_override is not False
                or self.retry_automatically is not False):
            raise ValueError("Scanner failure responses must remain fail-closed.")


SCANNER_FAILURE_RESPONSES = MappingProxyType({
    ScannerFailureKind.INITIALIZATION_FAILED: ScannerFailureResponse(
        ScanResultStatus.scanFailed, INITIALIZATION_MESSAGE
    ),
    ScannerFailureKind.PROCESS_FAILED: ScannerFailureResponse(
        ScanResultStatus.scanFailed, PROCESS_MESSAGE
    ),
    ScannerFailureKind.INCOMPLETE_RESULT: ScannerFailureResponse(
        ScanResultStatus.incompleteScan, INCOMPLETE_MESSAGE
    ),
    ScannerFailureKind.TIMED_OUT: ScannerFailureResponse(
        ScanResultStatus.scanTimedOut, TIMEOUT_MESSAGE
    ),
})

UNKNOWN_SCANNER_FAILURE_RESPONSE = ScannerFailureResponse(
    ScanResultStatus.scanFailed, UNKNOWN_MESSAGE
)


def response_for_scanner_failure(kind: object) -> ScannerFailureResponse:
    """Reject unknown/untrusted failures; never infer a clean result from text."""
    if not isinstance(kind, ScannerFailureKind):
        return UNKNOWN_SCANNER_FAILURE_RESPONSE
    return SCANNER_FAILURE_RESPONSES.get(kind, UNKNOWN_SCANNER_FAILURE_RESPONSE)
