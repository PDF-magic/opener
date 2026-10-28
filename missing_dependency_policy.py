"""Declarative fail-closed responses for unavailable required protection controls.

This defines response policy, not a dependency detector or an active profile.
The existing ClamAV gate retains exclusive responsibility for scanning.
"""

from dataclasses import dataclass
from enum import Enum
from types import MappingProxyType
from typing import Mapping

from protection_policy_definitions import PolicyControl
from scan_results import ScanResultStatus


class MissingDependencyDisposition(str, Enum):
    DENY = "deny"


# Fixed, path-free user-facing text: never include untrusted diagnostics.
_RESPONSE_SPECS: Mapping[PolicyControl, tuple[ScanResultStatus, str]] = MappingProxyType({
    PolicyControl.CLAMAV_SCAN_GATE: (
        ScanResultStatus.scanFailed,
        "The required malware scanner is unavailable; opening was stopped. "
        "Reinstall PDF Magic Opener.",
    ),
    PolicyControl.SIGNATURE_FRESHNESS: (
        ScanResultStatus.scanFailed,
        "Required malware signatures are unavailable or unverified; opening "
        "was stopped. Update the malware signatures.",
    ),
    PolicyControl.FILE_INTEGRITY: (
        ScanResultStatus.incompleteScan,
        "Required file integrity verification could not run; opening was "
        "stopped. Restore the scanning components before retrying.",
    ),
    PolicyControl.FAIL_CLOSED_HANDOFF: (
        ScanResultStatus.scanFailed,
        "The verified document handoff is unavailable; opening was stopped. "
        "Restore the application or select a supported destination.",
    ),
    PolicyControl.PDF_STRUCTURE_VALIDATION: (
        ScanResultStatus.incompleteScan,
        "Required PDF structure inspection is unavailable; opening was "
        "stopped. This protection check must be implemented before use.",
    ),
    PolicyControl.ISOLATED_BEHAVIOR_ANALYSIS: (
        ScanResultStatus.incompleteScan,
        "Required isolated behavior analysis is unavailable; opening was "
        "stopped. This protection check must be implemented before use.",
    ),
})

_GENERIC_RESPONSE_SPEC = (
    ScanResultStatus.scanFailed,
    "A required protection dependency is unavailable; opening was stopped. "
    "Restore the required protection components before retrying.",
)

if set(_RESPONSE_SPECS) != set(PolicyControl):
    raise ValueError("Each protection control needs a missing-dependency response")


@dataclass(frozen=True)
class MissingDependencyResponse:
    """Refuse missing required checks, without relaxing the scan gate."""

    control: PolicyControl | None
    scan_status: ScanResultStatus
    user_message: str
    disposition: MissingDependencyDisposition = MissingDependencyDisposition.DENY
    show_failure_alert: bool = True
    preserve_quarantine: bool = True
    allow_open: bool = False
    allow_clean_cache: bool = False
    allow_quarantine_release: bool = False
    allow_fallback: bool = False
    allow_override: bool = False
    retry_automatically: bool = False

    def __post_init__(self) -> None:
        if self.control is not None and not isinstance(self.control, PolicyControl):
            raise TypeError("A validated protection control is required.")
        expected = (_GENERIC_RESPONSE_SPEC if self.control is None else
                    _RESPONSE_SPECS[self.control])
        # ScanResultStatus subclasses str; equality alone would accept a raw
        # "scanFailed" string as though it were a validated canonical outcome.
        if (self.scan_status is not expected[0] or
                type(self.user_message) is not str or
                self.user_message != expected[1]):
            raise ValueError("Missing dependencies need their fixed non-clean outcome.")
        if (self.disposition is not MissingDependencyDisposition.DENY or
                self.show_failure_alert is not True or
                self.preserve_quarantine is not True or
                self.allow_open is not False or
                self.allow_clean_cache is not False or
                self.allow_quarantine_release is not False or
                self.allow_fallback is not False or
                self.allow_override is not False or
                self.retry_automatically is not False):
            raise ValueError("A missing required dependency must never permit opening.")

    def as_document(self) -> dict:
        """Return detached JSON-compatible metadata, not executable behavior."""
        return {
            "control": self.control.value if self.control is not None else "unknown",
            "scan_status": self.scan_status.value,
            "user_message": self.user_message,
            "disposition": self.disposition.value,
            "show_failure_alert": self.show_failure_alert,
            "preserve_quarantine": self.preserve_quarantine,
            "allow_open": self.allow_open,
            "allow_clean_cache": self.allow_clean_cache,
            "allow_quarantine_release": self.allow_quarantine_release,
            "allow_fallback": self.allow_fallback,
            "allow_override": self.allow_override,
            "retry_automatically": self.retry_automatically,
        }


MISSING_DEPENDENCY_RESPONSES: Mapping[PolicyControl, MissingDependencyResponse] = (
    MappingProxyType({
        control: MissingDependencyResponse(control, status, message)
        for control, (status, message) in _RESPONSE_SPECS.items()
    })
)

UNKNOWN_MISSING_DEPENDENCY_RESPONSE = MissingDependencyResponse(
    None, *_GENERIC_RESPONSE_SPEC
)


def response_for_missing_dependency(control: object) -> MissingDependencyResponse:
    """Fail closed for unknown inputs; call only for an effective REQUIRED check.

    Optional, planned checks are not made active or required by this definition.
    """
    if not isinstance(control, PolicyControl):
        return UNKNOWN_MISSING_DEPENDENCY_RESPONSE
    return MISSING_DEPENDENCY_RESPONSES.get(
        control, UNKNOWN_MISSING_DEPENDENCY_RESPONSE
    )
