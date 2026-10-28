"""Declarative maximum processing times for protection-policy stages.

These are proposed per-stage budgets, NOT live deadlines or a profile switch.
The installed PDF scanner already has a 30-minute subprocess timeout; no
other stage's budget is currently enforced by this catalog. An implementation
must use monotonic deadlines, abort safely on expiry and never interpret a
timeout as a clean result. Enforcement belongs to a separate task.
"""

from dataclasses import dataclass
from enum import Enum
from types import MappingProxyType
from typing import Mapping

from protection_profiles import ProtectionProfileID
from protection_policy_definitions import (
    ControlAvailability,
    PolicyControl,
    PROTECTION_POLICIES,
)


STAGE_TIME_LIMIT_SCHEMA_VERSION = 1

# Maximum elapsed seconds per attempted stage. These caps are intended for
# PDF protection workflows, not the separately supported application-bundle
# scan path. ClamAV matches the existing PDF_SCAN_TIMEOUT = 30 * 60 runtime
# limit; other caps are definitions only and are NOT yet enforced.
STAGE_MAXIMUM_SECONDS: Mapping[PolicyControl, int] = MappingProxyType({
    PolicyControl.SIGNATURE_FRESHNESS: 20,
    PolicyControl.FILE_INTEGRITY: 300,
    PolicyControl.CLAMAV_SCAN_GATE: 1800,
    PolicyControl.PDF_STRUCTURE_VALIDATION: 120,
    PolicyControl.ISOLATED_BEHAVIOR_ANALYSIS: 600,
    PolicyControl.FAIL_CLOSED_HANDOFF: 60,
})


@dataclass(frozen=True)
class ProcessingStageLimit:
    control: PolicyControl
    maximum_seconds: int
    availability: ControlAvailability

    def __post_init__(self):
        if not isinstance(self.control, PolicyControl):
            raise TypeError("A known policy control is required")
        if type(self.maximum_seconds) is not int or self.maximum_seconds <= 0:
            raise ValueError("Each stage must have a finite positive integer timeout")
        if not isinstance(self.availability, ControlAvailability):
            raise TypeError("Stage availability must be declared explicitly")
        if self.maximum_seconds != STAGE_MAXIMUM_SECONDS[self.control]:
            raise ValueError("Stage time limit must match the versioned policy budget")

    def as_document(self) -> dict:
        return {
            "control": self.control.value,
            "maximum_seconds": self.maximum_seconds,
            "availability": self.availability.value,
        }


@dataclass(frozen=True)
class ProfileStageLimits:
    profile_id: ProtectionProfileID
    stages: tuple[ProcessingStageLimit, ...]
    schema_version: int = STAGE_TIME_LIMIT_SCHEMA_VERSION

    def __post_init__(self):
        if not isinstance(self.profile_id, ProtectionProfileID):
            raise TypeError("A validated profile identifier is required")
        if type(self.schema_version) is not int or self.schema_version != STAGE_TIME_LIMIT_SCHEMA_VERSION:
            raise ValueError("Unsupported stage time limit schema version")
        if not isinstance(self.stages, tuple):
            raise TypeError("Stage limits must be an immutable tuple")
        if any(not isinstance(stage, ProcessingStageLimit) for stage in self.stages):
            raise TypeError("Invalid stage limit entry")
        expected = PROTECTION_POLICIES[self.profile_id].requirements
        actual = tuple((stage.control, stage.availability) for stage in self.stages)
        required = tuple((item.control, item.availability) for item in expected)
        if actual != required:
            raise ValueError("Every required policy stage needs exactly one matching time limit")

    def as_document(self) -> dict:
        """Produce detached, JSON-safe metadata, not an executable policy."""
        return {
            "schema_version": self.schema_version,
            "profile_id": self.profile_id.value,
            "stages": [stage.as_document() for stage in self.stages],
        }


def _limits_for(profile_id: ProtectionProfileID) -> ProfileStageLimits:
    return ProfileStageLimits(
        profile_id=profile_id,
        stages=tuple(
            ProcessingStageLimit(
                control=entry.control,
                maximum_seconds=STAGE_MAXIMUM_SECONDS[entry.control],
                availability=entry.availability,
            )
            for entry in PROTECTION_POLICIES[profile_id].requirements
        ),
    )


PROFILE_STAGE_LIMITS: Mapping[ProtectionProfileID, ProfileStageLimits] = MappingProxyType({
    profile_id: _limits_for(profile_id) for profile_id in ProtectionProfileID
})

if set(STAGE_MAXIMUM_SECONDS) != set(PolicyControl):
    raise ValueError("Every known stage must have a maximum processing time")
if set(PROFILE_STAGE_LIMITS) != set(PROTECTION_POLICIES):
    raise ValueError("Each profile must have a complete stage limit definition")


def stage_limits_for_profile(profile_id: ProtectionProfileID) -> ProfileStageLimits:
    """Get immutable proposed limits; does not initiate or authorize scanning."""
    if not isinstance(profile_id, ProtectionProfileID):
        raise TypeError("A validated profile identifier is required")
    return PROFILE_STAGE_LIMITS[profile_id]
