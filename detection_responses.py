"""Declarative responses for every canonical scan outcome (opener-0253).

This is a read-only response contract, not a new scanner or policy dispatcher.
The installed scanner continues to own verdicts, quarantine and file handoff.
A clean result still must pass the existing identity, destination and quarantine
checks; none of these responses opens a document by itself.
"""

from dataclasses import dataclass
from enum import Enum
from types import MappingProxyType

from scan_results import ScanResultStatus


class DetectionAction(str, Enum):
    """What a caller should do after a trusted terminal scan outcome."""

    VERIFY_BEFORE_HANDOFF = "verifyBeforeHandoff"
    DENY_OPEN = "denyOpen"
    STOP_CANCELLED = "stopCancelled"


@dataclass(frozen=True)
class DetectionResponse:
    """Immutable, path-free guidance; never an authorization to skip checks."""

    action: DetectionAction
    user_message: str
    show_failure_alert: bool
    preserve_quarantine: bool = True


# A clean verdict continues to the *existing* safety gates, never directly
# launches or clears quarantine. Every other outcome denies that handoff.
_RESPONSES = MappingProxyType({
    ScanResultStatus.clean: DetectionResponse(
        DetectionAction.VERIFY_BEFORE_HANDOFF,
        "Required scanning completed without a detected threat; verify the file "
        "and selected destination before opening.",
        False,
    ),
    ScanResultStatus.malwareDetected: DetectionResponse(
        DetectionAction.DENY_OPEN,
        "Malware was detected; the document was not opened.",
        True,
    ),
    ScanResultStatus.suspiciousStructure: DetectionResponse(
        DetectionAction.DENY_OPEN,
        "The document has a suspicious or malformed structure; opening was stopped.",
        True,
    ),
    ScanResultStatus.encrypted: DetectionResponse(
        DetectionAction.DENY_OPEN,
        "Required inspection was blocked by encryption; opening was stopped.",
        True,
    ),
    ScanResultStatus.incompleteScan: DetectionResponse(
        DetectionAction.DENY_OPEN,
        "The safety scan was incomplete; opening was stopped.",
        True,
    ),
    ScanResultStatus.scanFailed: DetectionResponse(
        DetectionAction.DENY_OPEN,
        "The scanner or a required safety check failed; opening was stopped.",
        True,
    ),
    ScanResultStatus.scanTimedOut: DetectionResponse(
        DetectionAction.DENY_OPEN,
        "The safety scan timed out; opening was stopped.",
        True,
    ),
    ScanResultStatus.fileChanged: DetectionResponse(
        DetectionAction.DENY_OPEN,
        "The file changed during verification; opening was stopped.",
        True,
    ),
    ScanResultStatus.fileTooLarge: DetectionResponse(
        DetectionAction.DENY_OPEN,
        "The file exceeded a safety-scanning size limit; opening was stopped.",
        True,
    ),
    ScanResultStatus.cancelled: DetectionResponse(
        DetectionAction.STOP_CANCELLED,
        "Scanning was cancelled; the document was not opened.",
        False,
    ),
})

_UNKNOWN_RESPONSE = DetectionResponse(
    DetectionAction.DENY_OPEN,
    "The scan result could not be verified; opening was stopped.",
    True,
)


def response_for_detection(status: ScanResultStatus) -> DetectionResponse:
    """Return guidance only for trusted canonical outcomes.

    Unknown, untrusted or string-only values fail closed, including the
    string "clean". Callers must establish a trusted ScanResultStatus before
    even considering the independent open/quarantine verification gates.
    """
    if not isinstance(status, ScanResultStatus):
        return _UNKNOWN_RESPONSE
    return _RESPONSES.get(status, _UNKNOWN_RESPONSE)
