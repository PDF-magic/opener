"""Exhaustive, passive blocking policy for validated Enhanced findings (opener-0300).

The rule table determines whether each finding is a routine observation,
requires review before opening, or unconditionally blocks. Both non-routine
outcomes block pending further assessment. This is neither a clean verdict
nor an authorization, and does not activate Enhanced or alter Built-in scans.
"""

from dataclasses import dataclass, field
from enum import Enum
from types import MappingProxyType

from enhanced_analysis_findings import (
    AnalysisFinding, AnalysisStage, FindingCode, FindingSeverity,
    StructuredAnalysisFindings,
)
from enhanced_additional_inspections import plan_additional_inspections
from enhanced_inconclusive_results import assess_inconclusive_opening


class BlockingDisposition(str, Enum):
    """Review is also blocking until separately resolved by a trusted policy."""

    observation = "observation"
    holdForReview = "holdForReview"
    denyOpening = "denyOpening"


# Fixed, independently reviewed policy for *every* finding code. The values
# are minimum dispositions: a finding's blocking or critical severity always
# upgrades to denyOpening, and review-required/suspicious severities cannot be observational.
# A producer cannot downgrade structural failures or unresolved inspections
# by marking them informational. No table value means "safe" or "allow".
_MINIMUM_DISPOSITION = MappingProxyType({
    FindingCode.malformedStructure: BlockingDisposition.denyOpening,
    FindingCode.conflictingStructure: BlockingDisposition.denyOpening,
    FindingCode.unresolvedReference: BlockingDisposition.denyOpening,
    FindingCode.activeContent: BlockingDisposition.holdForReview,
    FindingCode.suspiciousUrl: BlockingDisposition.holdForReview,
    FindingCode.unexpectedEmbeddedFile: BlockingDisposition.holdForReview,
    FindingCode.incrementalRevision: BlockingDisposition.observation,
    FindingCode.unsupportedFeature: BlockingDisposition.denyOpening,
    FindingCode.resourceLimit: BlockingDisposition.denyOpening,
    FindingCode.inspectionFailure: BlockingDisposition.denyOpening,
})

if set(_MINIMUM_DISPOSITION) != set(FindingCode):
    raise RuntimeError("Every Enhanced finding code needs an explicit blocking rule")


def disposition_for_finding(finding: AnalysisFinding) -> BlockingDisposition:
    """Classify trusted, typed evidence; never trust arbitrary PDF text/JSON."""
    if type(finding) is not AnalysisFinding:
        raise TypeError("Blocking policy requires validated AnalysisFinding evidence")
    minimum = _MINIMUM_DISPOSITION[finding.code]
    if minimum is BlockingDisposition.denyOpening or finding.severity in (
        FindingSeverity.blocking, FindingSeverity.critical
    ):
        return BlockingDisposition.denyOpening
    if minimum is BlockingDisposition.holdForReview or (
        finding.severity in (FindingSeverity.reviewRequired, FindingSeverity.suspicious)
    ):
        return BlockingDisposition.holdForReview
    return BlockingDisposition.observation


@dataclass(frozen=True)
class FindingBlockingDecision:
    """Preserve one finding's order, location and fixed category without raw text."""

    source_stage: AnalysisStage
    finding: AnalysisFinding
    disposition: BlockingDisposition = field(init=False)

    def __post_init__(self) -> None:
        if type(self.source_stage) is not AnalysisStage:
            raise TypeError("Source stage must be a validated AnalysisStage")
        object.__setattr__(
            self, "disposition", disposition_for_finding(self.finding)
        )

    @property
    def requires_block(self) -> bool:
        return self.disposition is not BlockingDisposition.observation

    def to_dict(self) -> dict:
        return {
            "sourceStage": self.source_stage.value,
            **self.finding.to_dict(),
            "disposition": self.disposition.value,
            "requiresBlock": self.requires_block,
        }


@dataclass(frozen=True)
class EnhancedBlockingPolicy:
    """Aggregate all finding and missing-stage blockers without authorizing open.

    The older inconclusive-evidence and follow-up policies remain independent
    safety floors, never alternatives to the explicit per-finding rules.
    """

    source: StructuredAnalysisFindings
    findings: tuple[FindingBlockingDecision, ...] = field(init=False)
    requires_block: bool = field(init=False)

    def __post_init__(self) -> None:
        if type(self.source) is not StructuredAnalysisFindings:
            raise TypeError("Expected validated structured Enhanced analysis")
        by_stage = {stage.stage: stage for stage in self.source.stages}
        results = tuple(
            FindingBlockingDecision(stage, finding)
            for stage in self.source.expected_stages
            if stage in by_stage
            for finding in by_stage[stage].findings
        )
        previous_block = (
            self.source.requires_block
            or assess_inconclusive_opening(self.source).requires_block
            or plan_additional_inspections(self.source).requires_block
        )
        object.__setattr__(self, "findings", results)
        object.__setattr__(
            self, "requires_block",
            bool(self.source.incomplete_stages)
            or any(item.requires_block for item in results)
            or previous_block,
        )

    @property
    def incomplete_stages(self) -> tuple[AnalysisStage, ...]:
        return self.source.incomplete_stages

    @property
    def blocking_findings(self) -> tuple[FindingBlockingDecision, ...]:
        return tuple(item for item in self.findings if item.requires_block)

    @property
    def authorizes_open(self) -> bool:
        return False

    def to_dict(self) -> dict:
        return {
            "schemaVersion": 1,
            "requiresBlock": self.requires_block,
            "authorizesOpen": False,
            "incompleteStages": [stage.value for stage in self.incomplete_stages],
            "findings": [item.to_dict() for item in self.findings],
        }


def determine_blocking_findings(
    report: StructuredAnalysisFindings,
) -> EnhancedBlockingPolicy:
    """Decide which Enhanced findings require blocking; never open a PDF."""
    return EnhancedBlockingPolicy(report)
