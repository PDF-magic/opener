"""Immutable, non-executable resource budgets for protection policy stages.

The six stages are PolicyControl values, not the separate file lifecycle states.
Only the ClamAV concurrency ceiling is already enforced. All other numerical
ceilings are design targets; the installed scanner has no application-configured
CPU, memory or temporary-disk limits. Wall-time limits are owned separately by
the stage-time-limit contract (opener-0257), not duplicated here.

This module cannot select a profile, execute checks, or authorize file opening.
"""

from dataclasses import dataclass
from enum import Enum
from types import MappingProxyType
from typing import Mapping

from protection_profiles import ProtectionProfileID
from protection_policy_definitions import (
    BASELINE_CONTROLS,
    ControlAvailability,
    PolicyControl,
    PROTECTION_POLICIES,
)


RESOURCE_BUDGET_SCHEMA_VERSION = 1


class ResourceEnforcement(str, Enum):
    CURRENT = "current"
    PLANNED = "planned"
    NOT_CONFIGURED = "not_configured"
    NOT_APPLICABLE = "not_applicable"


@dataclass(frozen=True)
class ResourceCeiling:
    maximum: int | None
    enforcement: ResourceEnforcement

    def __post_init__(self) -> None:
        if not isinstance(self.enforcement, ResourceEnforcement):
            raise TypeError("Resource ceilings need an explicit enforcement status")
        if self.enforcement in (ResourceEnforcement.CURRENT, ResourceEnforcement.PLANNED):
            if type(self.maximum) is not int or self.maximum <= 0:
                raise ValueError("An enforced or planned ceiling requires a positive integer")
        elif self.maximum is not None:
            raise ValueError("Unconfigured or inapplicable resources have no numeric ceiling")

    def as_document(self) -> dict:
        return {"maximum": self.maximum, "enforcement": self.enforcement.value}


@dataclass(frozen=True)
class ProtectionStageResources:
    """Per-attempt resource intent, never a scanner execution rule."""

    control: PolicyControl
    availability: ControlAvailability
    cpu_seconds: ResourceCeiling
    memory_mib: ResourceCeiling
    temporary_disk_mib: ResourceCeiling
    concurrent_requests: ResourceCeiling

    def __post_init__(self) -> None:
        if not isinstance(self.control, PolicyControl):
            raise TypeError("Resource budgets require a known protection stage")
        if not isinstance(self.availability, ControlAvailability):
            raise TypeError("Stage availability must be declared")
        expected_availability = (
            ControlAvailability.CURRENT if self.control in BASELINE_CONTROLS
            else ControlAvailability.PLANNED
        )
        if self.availability is not expected_availability:
            raise ValueError("Resources cannot activate unimplemented protection controls")
        fields = (
            self.cpu_seconds, self.memory_mib,
            self.temporary_disk_mib, self.concurrent_requests,
        )
        if any(not isinstance(item, ResourceCeiling) for item in fields):
            raise TypeError("Every resource dimension requires a typed ceiling")
        current = tuple(
            index for index, item in enumerate(fields)
            if item.enforcement is ResourceEnforcement.CURRENT
        )
        if self.control is PolicyControl.CLAMAV_SCAN_GATE:
            # The only actual resource ceiling is the two-scan gate; neither
            # the CPU, memory nor scratch disk has an app-enforced limit.
            if current != (3,) or self.concurrent_requests.maximum != 2:
                raise ValueError("Only the actual two-scan limit may be called enforced")
        elif current:
            raise ValueError("Non-scanner resource limits are still unenforced")

    def as_document(self) -> dict:
        """Detached, JSON-compatible metadata; no side effects."""
        return {
            "schema_version": RESOURCE_BUDGET_SCHEMA_VERSION,
            "control": self.control.value,
            "availability": self.availability.value,
            "cpu_seconds": self.cpu_seconds.as_document(),
            "memory_mib": self.memory_mib.as_document(),
            "temporary_disk_mib": self.temporary_disk_mib.as_document(),
            "concurrent_requests": self.concurrent_requests.as_document(),
        }


def _planned(maximum: int) -> ResourceCeiling:
    return ResourceCeiling(maximum, ResourceEnforcement.PLANNED)


_UNSET = ResourceCeiling(None, ResourceEnforcement.NOT_CONFIGURED)
_UNUSED = ResourceCeiling(None, ResourceEnforcement.NOT_APPLICABLE)


# Initial design targets, in per-stage/per-request units. Wall-time budgets
# belong to opener-0257 and may be more restrictive than CPU budgets.
# These ceilings are not applied by the current scanner or Settings app.
PROTECTION_STAGE_RESOURCES: Mapping[PolicyControl, ProtectionStageResources] = (
    MappingProxyType({
        PolicyControl.SIGNATURE_FRESHNESS: ProtectionStageResources(
            PolicyControl.SIGNATURE_FRESHNESS, ControlAvailability.CURRENT,
            _planned(5), _planned(64), _UNUSED, _planned(2),
        ),
        PolicyControl.FILE_INTEGRITY: ProtectionStageResources(
            PolicyControl.FILE_INTEGRITY, ControlAvailability.CURRENT,
            _planned(120), _planned(256), _planned(16), _planned(2),
        ),
        PolicyControl.CLAMAV_SCAN_GATE: ProtectionStageResources(
            PolicyControl.CLAMAV_SCAN_GATE, ControlAvailability.CURRENT,
            _UNSET, _UNSET, _UNSET,
            ResourceCeiling(2, ResourceEnforcement.CURRENT),
        ),
        PolicyControl.PDF_STRUCTURE_VALIDATION: ProtectionStageResources(
            PolicyControl.PDF_STRUCTURE_VALIDATION, ControlAvailability.PLANNED,
            _planned(90), _planned(256), _planned(512), _planned(1),
        ),
        PolicyControl.ISOLATED_BEHAVIOR_ANALYSIS: ProtectionStageResources(
            PolicyControl.ISOLATED_BEHAVIOR_ANALYSIS, ControlAvailability.PLANNED,
            _planned(300), _planned(1024), _planned(2048), _planned(1),
        ),
        PolicyControl.FAIL_CLOSED_HANDOFF: ProtectionStageResources(
            PolicyControl.FAIL_CLOSED_HANDOFF, ControlAvailability.CURRENT,
            _planned(10), _planned(128), _UNUSED, _planned(2),
        ),
    })
)

if set(PROTECTION_STAGE_RESOURCES) != set(PolicyControl):
    raise ValueError("Each protection stage must have a resource budget")
if any(key is not stage.control for key, stage in PROTECTION_STAGE_RESOURCES.items()):
    raise ValueError("Protection stage budget key differs from the stage")


def resource_budget_for_stage(control: PolicyControl) -> ProtectionStageResources:
    """Read-only contract lookup, not scan enforcement."""
    if not isinstance(control, PolicyControl):
        raise TypeError("A validated protection stage is required")
    return PROTECTION_STAGE_RESOURCES[control]


def resource_budgets_for_profile(
    profile_id: ProtectionProfileID,
) -> tuple[ProtectionStageResources, ...]:
    """Stages required by the inactive profile, in policy order."""
    if not isinstance(profile_id, ProtectionProfileID):
        raise TypeError("A validated protection profile is required")
    requirements = PROTECTION_POLICIES[profile_id].requirements
    stages = tuple(PROTECTION_STAGE_RESOURCES[item.control] for item in requirements)
    if any(stage.availability is not item.availability
           for stage, item in zip(stages, requirements)):
        raise ValueError("The budget does not match the protection profile requirements")
    return stages
