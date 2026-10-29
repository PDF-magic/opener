"""Keep scanner failures separate from unsupported feature-exception requests.

opener-0344 is a presentation-only fail-closed classifier. It does not
implement exceptions, infer a scan verdict, replace ClamAV, or authorize opening.
The installed scan gate and scanner_failure_policy are always authoritative.
"""

from dataclasses import dataclass
from enum import Enum

from scan_results import ScanResultStatus
from scanner_failure_policy import (
    ScannerFailureKind,
    UNKNOWN_SCANNER_FAILURE_RESPONSE,
    response_for_scanner_failure,
)

EXCEPTION_REJECTION_MESSAGE = (
    "Feature exceptions are not supported; mandatory scanning remains required."
)


class ProtectionBlockOrigin(str, Enum):
    SCANNER_FAILURE = "scannerFailure"
    FEATURE_EXCEPTION_REJECTED = "featureExceptionRejected"


@dataclass(frozen=True)
class ProtectionBlockReport:
    """Immutable diagnostic; neither origin can authorize an open or bypass."""

    origin: ProtectionBlockOrigin
    scan_status: ScanResultStatus | None
    message: str

    def __post_init__(self):
        if type(self.origin) is not ProtectionBlockOrigin:
            raise ValueError("Known block origin required")
        if self.origin is ProtectionBlockOrigin.SCANNER_FAILURE:
            from scanner_failure_policy import SCANNER_FAILURE_RESPONSES
            approved = tuple(x.user_message for x in SCANNER_FAILURE_RESPONSES.values())
            approved += (UNKNOWN_SCANNER_FAILURE_RESPONSE.user_message,)
            if (type(self.scan_status) is not ScanResultStatus or
                    self.scan_status not in (
                        ScanResultStatus.scanFailed,
                        ScanResultStatus.scanTimedOut,
                        ScanResultStatus.incompleteScan,
                    ) or self.message not in approved or not any(
                        x.user_message == self.message and x.scan_status is self.scan_status
                        for x in (*SCANNER_FAILURE_RESPONSES.values(),
                                  UNKNOWN_SCANNER_FAILURE_RESPONSE)
                    )):
                raise ValueError("Scanner failure must retain its specific denial status")
        else:
            if (self.scan_status is not None or
                    self.message != EXCEPTION_REJECTION_MESSAGE):
                raise ValueError("A rejected exception is not a scanner verdict")

    @property
    def authorizes_open(self) -> bool:
        return False

    @property
    def user_exception_approved(self) -> bool:
        return False

    def to_dict(self) -> dict:
        """Fixed path-free presentation metadata; no raw exception request."""
        return {
            "origin": self.origin.value,
            "scanStatus": self.scan_status.value if self.scan_status else None,
            "message": self.message,
            "authorizesOpen": False,
            "userExceptionApproved": False,
        }


def report_protection_block(
    scanner_failure: object = None, *,
    feature_exception_request: object = None,
) -> ProtectionBlockReport | None:
    """Scanner failures take priority; no exception request can suppress one.

    A caller must supply a trusted failure enum if a scanner failure occurred.
    Any non-None untrusted failure token is mapped to the fixed unknown failure
    response. A feature exception request is *never* inspected or approved,
    even when labelled 'user-approved' by its source.
    """
    if scanner_failure is not None:
        response = response_for_scanner_failure(scanner_failure)
        return ProtectionBlockReport(
            ProtectionBlockOrigin.SCANNER_FAILURE,
            response.scan_status,
            response.user_message,
        )
    if feature_exception_request is not None:
        return ProtectionBlockReport(
            ProtectionBlockOrigin.FEATURE_EXCEPTION_REJECTED,
            None,
            EXCEPTION_REJECTION_MESSAGE,
        )
    # No reported block is not a clean verdict; the scanner still decides.
    return None
