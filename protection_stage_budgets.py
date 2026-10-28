"""Non-executable resource budgets for the seven file lifecycle stages.

This is an immutable policy-planning contract, not a resource limiter. Only
CURRENT ceilings describe constraints already enforced by scan-and-open.py.
PLANNED ceilings are design targets, not active protections. NOT_CONFIGURED
means this application sets no explicit bound; OS/ClamAV limits can still apply.
No profile selection, scanner behavior, persistence, or quarantine rule changes.
"""

from dataclasses import dataclass
from enum import Enum
from types import MappingProxyType
from typing import Mapping

from file_lifecycle import FileState


BUDGET_SCHEMA_VERSION = 1


class BudgetEnforcement(str, Enum):
    CURRENT = "current"
    PLANNED = "planned"
    NOT_CONFIGURED = "not_configured"
    NOT_APPLICABLE = "not_applicable"


@dataclass(frozen=True)
class ResourceCeiling:
    limit: int | None
    enforcement: BudgetEnforcement

    def __post_init__(self) -> None:
        if not isinstance(self.enforcement, BudgetEnforcement):
            raise TypeError("Resource budget requires a valid enforcement status")
        if self.enforcement in (BudgetEnforcement.CURRENT, BudgetEnforcement.PLANNED):
            if type(self.limit) is not int or self.limit <= 0:
                raise ValueError("A bounded resource must have a positive integer limit")
        elif self.limit is not None:
            raise ValueError("Unconfigured or inapplicable resources cannot claim a limit")

    def as_document(self) -> dict:
        return {"limit": self.limit, "enforcement": self.enforcement.value}


@dataclass(frozen=True)
class StageResourceBudget:
    stage: FileState
    pdf_wall_seconds: ResourceCeiling
    other_wall_seconds: ResourceCeiling
    cpu_seconds: ResourceCeiling
    memory_mib: ResourceCeiling
    concurrent_requests: ResourceCeiling

    def __post_init__(self) -> None:
        if not isinstance(self.stage, FileState):
            raise TypeError("Stage budgets require a known file lifecycle state")
        resources = (
            self.pdf_wall_seconds, self.other_wall_seconds,
            self.cpu_seconds, self.memory_mib, self.concurrent_requests,
        )
        if any(not isinstance(resource, ResourceCeiling) for resource in resources):
            raise TypeError("Every stage resource must have an explicit ceiling status")
        if self.stage in (FileState.BLOCKED, FileState.COMPLETED) and any(
            item.enforcement is not BudgetEnforcement.NOT_APPLICABLE
            for item in resources
        ):
            raise ValueError("Terminal lifecycle states have no processing budget")

    def as_document(self) -> dict:
        """Return a detached JSON-serializable description; never activate limits."""
        return {
            "schema_version": BUDGET_SCHEMA_VERSION,
            "stage": self.stage.value,
            "pdf_wall_seconds": self.pdf_wall_seconds.as_document(),
            "other_wall_seconds": self.other_wall_seconds.as_document(),
            "cpu_seconds": self.cpu_seconds.as_document(),
            "memory_mib": self.memory_mib.as_document(),
            "concurrent_requests": self.concurrent_requests.as_document(),
        }


def _current(limit: int) -> ResourceCeiling:
    return ResourceCeiling(limit, BudgetEnforcement.CURRENT)


def _planned(limit: int) -> ResourceCeiling:
    return ResourceCeiling(limit, BudgetEnforcement.PLANNED)


_UNSET = ResourceCeiling(None, BudgetEnforcement.NOT_CONFIGURED)
_INACTIVE = ResourceCeiling(None, BudgetEnforcement.NOT_APPLICABLE)


# The lifecycle is presently a declarative contract, not the running scan
# state machine. Planned limits below are initial *per-request stage* targets.
# Only SCANNING's existing timeouts and cross-process concurrency are CURRENT;
# the scanner has no app-configured CPU or memory ceiling.
STAGE_RESOURCE_BUDGETS: Mapping[FileState, StageResourceBudget] = MappingProxyType({
    FileState.QUEUED: StageResourceBudget(
        FileState.QUEUED, _planned(3600), _planned(3600),
        _INACTIVE, _planned(64), _UNSET,
    ),
    FileState.SCANNING: StageResourceBudget(
        FileState.SCANNING, _current(1800), _current(180),
        _UNSET, _UNSET, _current(2),
    ),
    FileState.ANALYZING: StageResourceBudget(
        FileState.ANALYZING, _planned(300), _planned(300),
        _planned(240), _planned(512), _planned(2),
    ),
    FileState.READY: StageResourceBudget(
        FileState.READY, _planned(30), _planned(30),
        _planned(10), _planned(64), _planned(2),
    ),
    FileState.OPENING: StageResourceBudget(
        FileState.OPENING, _planned(60), _planned(60),
        _planned(30), _planned(128), _planned(2),
    ),
    FileState.BLOCKED: StageResourceBudget(
        FileState.BLOCKED, _INACTIVE, _INACTIVE,
        _INACTIVE, _INACTIVE, _INACTIVE,
    ),
    FileState.COMPLETED: StageResourceBudget(
        FileState.COMPLETED, _INACTIVE, _INACTIVE,
        _INACTIVE, _INACTIVE, _INACTIVE,
    ),
})

if set(STAGE_RESOURCE_BUDGETS) != set(FileState):
    raise ValueError("Every file lifecycle state needs an explicit resource budget")
if any(state is not budget.stage for state, budget in STAGE_RESOURCE_BUDGETS.items()):
    raise ValueError("Resource budget stage does not match its registry key")


def stage_resource_budget(stage: FileState) -> StageResourceBudget:
    """Look up a budget descriptor without executing, selecting or enforcing it."""
    if not isinstance(stage, FileState):
        raise TypeError("A validated file lifecycle state is required")
    return STAGE_RESOURCE_BUDGETS[stage]
