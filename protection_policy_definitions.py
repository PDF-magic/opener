"""Structured, non-executable requirements for planned protection profiles.

This module describes future policy contracts only. Nothing here selects a
profile, changes persisted preferences, weakens the existing ClamAV scan gate,
or grants permission to open a PDF. The installed handler's Built-in policy
remains the only active protection mode until separately implemented and tested.
"""

from dataclasses import dataclass
from enum import Enum
from types import MappingProxyType
from typing import Mapping

from protection_profiles import (
    BASELINE_SAFETY_CHECKS,
    PROTECTION_PROFILES,
    ProtectionProfileID,
)


class PolicyControl(str, Enum):
    CLAMAV_SCAN_GATE = "clamav_scan_gate"
    SIGNATURE_FRESHNESS = "signature_freshness"
    FILE_INTEGRITY = "file_integrity"
    FAIL_CLOSED_HANDOFF = "fail_closed_handoff"
    # Proposed additional controls are NOT implemented by the scanner.
    PDF_STRUCTURE_VALIDATION = "pdf_structure_validation"
    ISOLATED_BEHAVIOR_ANALYSIS = "isolated_behavior_analysis"


class ControlAvailability(str, Enum):
    CURRENT = "current"
    PLANNED = "planned"


class FailureDisposition(str, Enum):
    DENY = "deny"


POLICY_SCHEMA_VERSION = 1

BASELINE_CONTROLS = (
    PolicyControl.CLAMAV_SCAN_GATE,
    PolicyControl.SIGNATURE_FRESHNESS,
    PolicyControl.FILE_INTEGRITY,
    PolicyControl.FAIL_CLOSED_HANDOFF,
)


# The deployed four-control floor is required in ALL profiles. Extra checks
# remain planned and non-executable; optional never means a bypass of the floor.
# The Maximum tier has no known optional extras, so its optional set is empty.
REQUIRED_CHECKS_BY_PROFILE: Mapping[ProtectionProfileID, frozenset[PolicyControl]] = (
    MappingProxyType({
        ProtectionProfileID.STANDARD: frozenset(BASELINE_CONTROLS),
        ProtectionProfileID.ENHANCED: frozenset((
            *BASELINE_CONTROLS, PolicyControl.PDF_STRUCTURE_VALIDATION,
        )),
        ProtectionProfileID.MAXIMUM: frozenset((
            *BASELINE_CONTROLS,
            PolicyControl.PDF_STRUCTURE_VALIDATION,
            PolicyControl.ISOLATED_BEHAVIOR_ANALYSIS,
        )),
    })
)
OPTIONAL_CHECKS_BY_PROFILE: Mapping[ProtectionProfileID, frozenset[PolicyControl]] = (
    MappingProxyType({
        ProtectionProfileID.STANDARD: frozenset({
            PolicyControl.PDF_STRUCTURE_VALIDATION,
        }),
        ProtectionProfileID.ENHANCED: frozenset({
            PolicyControl.ISOLATED_BEHAVIOR_ANALYSIS,
        }),
        ProtectionProfileID.MAXIMUM: frozenset(),
    })
)


@dataclass(frozen=True)
class PolicyRequirement:
    control: PolicyControl
    availability: ControlAvailability


@dataclass(frozen=True)
class StructuredProtectionPolicy:
    """Immutable intent, NOT an executable scan policy or authorization."""

    profile_id: ProtectionProfileID
    requirements: tuple[PolicyRequirement, ...]
    optional_checks: tuple[PolicyRequirement, ...] = ()
    schema_version: int = POLICY_SCHEMA_VERSION
    failure_disposition: FailureDisposition = FailureDisposition.DENY
    selectable: bool = False

    def __post_init__(self) -> None:
        if not isinstance(self.profile_id, ProtectionProfileID):
            raise TypeError("A validated protection profile identifier is required")
        if self.schema_version != POLICY_SCHEMA_VERSION:
            raise ValueError("Unsupported structured policy version")
        if self.failure_disposition is not FailureDisposition.DENY or self.selectable:
            raise ValueError("An inactive fail-closed policy cannot be weakened")
        if not isinstance(self.requirements, tuple):
            raise TypeError("Requirements must be an immutable tuple")
        if any(not isinstance(item, PolicyRequirement) or
               not isinstance(item.control, PolicyControl) or
               not isinstance(item.availability, ControlAvailability)
               for item in self.requirements):
            raise TypeError("Invalid control requirement")
        names = [item.control for item in self.requirements]
        if len(names) != len(set(names)):
            raise ValueError("Duplicate policy controls")
        current = frozenset(item.control.value for item in self.requirements
                            if item.availability is ControlAvailability.CURRENT)
        if current != BASELINE_SAFETY_CHECKS:
            raise ValueError("Current controls must match the mandatory safety floor")
        if any(item.control in BASELINE_CONTROLS and
               item.availability is not ControlAvailability.CURRENT
               for item in self.requirements):
            raise ValueError("Mandatory baseline controls cannot be merely planned")
        if not isinstance(self.optional_checks, tuple):
            raise TypeError("Optional checks must be an immutable tuple")
        if any(not isinstance(item, PolicyRequirement) or
               not isinstance(item.control, PolicyControl) or
               not isinstance(item.availability, ControlAvailability)
               for item in self.optional_checks):
            raise TypeError("Invalid optional control")
        optional_names = [item.control for item in self.optional_checks]
        if len(optional_names) != len(set(optional_names)):
            raise ValueError("Duplicate optional controls")
        if set(names) & set(optional_names):
            raise ValueError("A control cannot be both required and optional")
        if any(item.availability is not ControlAvailability.PLANNED or
               item.control in BASELINE_CONTROLS for item in self.optional_checks):
            raise ValueError("Optional checks must be planned, non-baseline controls")
        if frozenset(names) != REQUIRED_CHECKS_BY_PROFILE[self.profile_id]:
            raise ValueError("Required controls differ from the profile contract")
        if frozenset(optional_names) != OPTIONAL_CHECKS_BY_PROFILE[self.profile_id]:
            raise ValueError("Optional controls differ from the profile contract")

    @property
    def required_checks(self) -> tuple[PolicyRequirement, ...]:
        """Required metadata (including planned controls), not a scan verdict."""
        return self.requirements

    def as_document(self) -> dict:
        """Return a detached, JSON-serializable policy description."""
        return {
            "schema_version": self.schema_version,
            "profile_id": self.profile_id.value,
            "failure_disposition": self.failure_disposition.value,
            "selectable": self.selectable,
            "requirements": [
                {"control": item.control.value, "availability": item.availability.value}
                for item in self.requirements
            ],
            "optional_checks": [
                {"control": item.control.value, "availability": item.availability.value}
                for item in self.optional_checks
            ],
        }


def _required(*planned: PolicyControl) -> tuple[PolicyRequirement, ...]:
    return (
        *(PolicyRequirement(control, ControlAvailability.CURRENT)
          for control in BASELINE_CONTROLS),
        *(PolicyRequirement(control, ControlAvailability.PLANNED)
          for control in planned),
    )


def _optional(*planned: PolicyControl) -> tuple[PolicyRequirement, ...]:
    return tuple(
        PolicyRequirement(control, ControlAvailability.PLANNED)
        for control in planned
    )


# Structured policy differentiation is strictly declarative: Enhanced and
# Maximum carry plans for additional checks, never claims of live protection.
# Future work must implement and verify these controls before profile selection.
PROTECTION_POLICIES: Mapping[ProtectionProfileID, StructuredProtectionPolicy] = (
    MappingProxyType({
        ProtectionProfileID.STANDARD: StructuredProtectionPolicy(
            profile_id=ProtectionProfileID.STANDARD,
            requirements=_required(),
            optional_checks=_optional(PolicyControl.PDF_STRUCTURE_VALIDATION),
        ),
        ProtectionProfileID.ENHANCED: StructuredProtectionPolicy(
            profile_id=ProtectionProfileID.ENHANCED,
            requirements=_required(PolicyControl.PDF_STRUCTURE_VALIDATION),
            optional_checks=_optional(PolicyControl.ISOLATED_BEHAVIOR_ANALYSIS),
        ),
        ProtectionProfileID.MAXIMUM: StructuredProtectionPolicy(
            profile_id=ProtectionProfileID.MAXIMUM,
            requirements=_required(
                PolicyControl.PDF_STRUCTURE_VALIDATION,
                PolicyControl.ISOLATED_BEHAVIOR_ANALYSIS,
            ),
        ),
    })
)

# Detect drift between the catalog task and the structured definition task.
if set(PROTECTION_POLICIES) != set(PROTECTION_PROFILES):
    raise ValueError("Every catalog profile must have exactly one structured policy")
if frozenset(control.value for control in BASELINE_CONTROLS) != BASELINE_SAFETY_CHECKS:
    raise ValueError("Structured policy baseline differs from the active safety floor")
for _identifier, _policy in PROTECTION_POLICIES.items():
    if _policy.profile_id != _identifier or PROTECTION_PROFILES[_identifier].selectable:
        raise ValueError("Policy definition does not match its inactive catalog entry")
if set(REQUIRED_CHECKS_BY_PROFILE) != set(PROTECTION_PROFILES) or (
    set(OPTIONAL_CHECKS_BY_PROFILE) != set(PROTECTION_PROFILES)
):
    raise ValueError("Every protection profile must define required and optional checks")


def protection_policy_definition(profile_id: ProtectionProfileID) -> StructuredProtectionPolicy:
    """Read validated metadata; NEVER activate or apply a policy."""
    if not isinstance(profile_id, ProtectionProfileID):
        raise TypeError("A validated protection profile identifier is required")
    return PROTECTION_POLICIES[profile_id]
