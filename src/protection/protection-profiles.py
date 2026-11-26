"""Immutable definitions of planned protection tiers.

This catalog does NOT select a profile or alter scan policy. The installed
scan-and-open.py ClamAV gate remains the only enforcement authority; future
work must explicitly implement and test additional controls before making
any tier selectable or describing it as active.
"""

from dataclasses import dataclass
from enum import Enum
from types import MappingProxyType
from typing import Mapping


class ProtectionProfileID(str, Enum):
    """Stable identifiers for future persisted profile selections."""

    STANDARD = "standard"
    ENHANCED = "enhanced"
    MAXIMUM = "maximum"


@dataclass(frozen=True)
class ProtectionProfileDefinition:
    identifier: ProtectionProfileID
    display_name: str
    precedence: int
    summary: str
    required_safety_checks: frozenset[str]
    # A defined tier is not an executable or available scanner policy.
    selectable: bool = False


# Existing non-optional safety invariants. These names describe the current
# scan gate; this catalog never substitutes for checking their outcomes.
BASELINE_SAFETY_CHECKS = frozenset({
    "clamav_scan_gate",
    "signature_freshness",
    "file_integrity",
    "fail_closed_handoff",
})

PROTECTION_PROFILES: Mapping[ProtectionProfileID, ProtectionProfileDefinition] = (
    MappingProxyType({
        ProtectionProfileID.STANDARD: ProtectionProfileDefinition(
            identifier=ProtectionProfileID.STANDARD,
            display_name="Standard",
            precedence=1,
            summary="Baseline mandatory ClamAV scanning and fail-closed handoff.",
            required_safety_checks=BASELINE_SAFETY_CHECKS,
        ),
        ProtectionProfileID.ENHANCED: ProtectionProfileDefinition(
            identifier=ProtectionProfileID.ENHANCED,
            display_name="Enhanced",
            precedence=2,
            summary="Reserved intermediate tier; additional checks are not implemented.",
            required_safety_checks=BASELINE_SAFETY_CHECKS,
        ),
        ProtectionProfileID.MAXIMUM: ProtectionProfileDefinition(
            identifier=ProtectionProfileID.MAXIMUM,
            display_name="Maximum",
            precedence=3,
            summary="Reserved highest tier; additional checks are not implemented.",
            required_safety_checks=BASELINE_SAFETY_CHECKS,
        ),
    })
)


def protection_profile_definition(
    profile_id: ProtectionProfileID,
) -> ProtectionProfileDefinition:
    """Look up a named tier without changing the active scanner policy."""
    if not isinstance(profile_id, ProtectionProfileID):
        raise TypeError("Protection profiles require a validated profile identifier.")
    return PROTECTION_PROFILES[profile_id]
