"""Fail-closed response policy for PDF features that cannot be fully inspected.

These are response definitions, not PDF feature detectors, scanner overrides,
or selectable protection controls. Only trusted inspection evidence may
identify a feature; if inspection is incomplete, no clean verdict is valid.
The existing ClamAV scan gate remains the active enforcement mechanism.
"""

from dataclasses import dataclass
from enum import Enum
from types import MappingProxyType
from typing import Mapping

from scan_results import ScanResultStatus


class UnsupportedPDFFeature(str, Enum):
    """Stable categories for future verified PDF inspection findings."""

    UNSUPPORTED_FILTER = "unsupportedFilter"
    UNSUPPORTED_ACTIVE_CONTENT = "unsupportedActiveContent"
    UNSUPPORTED_EMBEDDED_CONTENT = "unsupportedEmbeddedContent"
    UNINSPECTABLE_ENCRYPTION = "uninspectableEncryption"
    INCOMPLETE_INSPECTION = "incompleteInspection"


class UnsupportedPDFAction(str, Enum):
    BLOCK = "block"


GENERIC_BLOCK_REASON = (
    "The PDF contains a feature that could not be fully inspected; "
    "opening was stopped."
)
ENCRYPTION_BLOCK_REASON = (
    "The PDF uses encryption that prevents required inspection; "
    "opening was stopped."
)


@dataclass(frozen=True)
class UnsupportedPDFResponse:
    """Terminal policy decision; never an authorization to bypass a scan."""

    action: UnsupportedPDFAction
    scan_status: ScanResultStatus
    reason: str
    preserve_quarantine: bool = True
    allow_clean_cache: bool = False
    allow_destination_handoff: bool = False
    allow_fallback: bool = False
    allow_override: bool = False

    def __post_init__(self) -> None:
        if self.action is not UnsupportedPDFAction.BLOCK:
            raise ValueError("Unsupported PDF features must block opening.")
        if self.scan_status not in (
            ScanResultStatus.incompleteScan, ScanResultStatus.encrypted
        ):
            raise ValueError("Unsupported features cannot produce a clean scan.")
        if self.reason not in (GENERIC_BLOCK_REASON, ENCRYPTION_BLOCK_REASON):
            raise ValueError("Only path-free user-facing reasons are permitted.")
        if self.scan_status is ScanResultStatus.encrypted:
            if self.reason != ENCRYPTION_BLOCK_REASON:
                raise ValueError("Encryption must use the encryption explanation.")
        elif self.reason != GENERIC_BLOCK_REASON:
            raise ValueError("Incomplete inspection must use the generic explanation.")
        if (
            not self.preserve_quarantine or self.allow_clean_cache or
            self.allow_destination_handoff or self.allow_fallback or
            self.allow_override
        ):
            raise ValueError("Unsupported features cannot weaken the scan gate.")

    @property
    def permits_open(self) -> bool:
        return False


INCOMPLETE_RESPONSE = UnsupportedPDFResponse(
    action=UnsupportedPDFAction.BLOCK,
    scan_status=ScanResultStatus.incompleteScan,
    reason=GENERIC_BLOCK_REASON,
)
ENCRYPTED_RESPONSE = UnsupportedPDFResponse(
    action=UnsupportedPDFAction.BLOCK,
    scan_status=ScanResultStatus.encrypted,
    reason=ENCRYPTION_BLOCK_REASON,
)

UNSUPPORTED_PDF_RESPONSES: Mapping[
    UnsupportedPDFFeature, UnsupportedPDFResponse
] = MappingProxyType({
    feature: (ENCRYPTED_RESPONSE if feature is
              UnsupportedPDFFeature.UNINSPECTABLE_ENCRYPTION
              else INCOMPLETE_RESPONSE)
    for feature in UnsupportedPDFFeature
})


def response_for_unsupported_pdf_feature(feature: object) -> UnsupportedPDFResponse:
    """Fail closed even for an unrecognized or malformed finding.

    A result here cannot substitute for the installed scanner or grant opening
    permission. An unrecognized feature never defaults to 'supported'.
    """
    if not isinstance(feature, UnsupportedPDFFeature):
        return INCOMPLETE_RESPONSE
    return UNSUPPORTED_PDF_RESPONSES[feature]
