"""Define conservative follow-up inspections for trusted Enhanced PDF findings.

This policy consumes structured findings but does not inspect a document,
activate Enhanced, satisfy a required check, or grant opening permission.
Only fixed enum identifiers appear in its output (opener-0301).
"""

from dataclasses import dataclass, field
from enum import Enum
from types import MappingProxyType

from enhanced_analysis_findings import (
    AnalysisFinding, AnalysisStage, FindingCode, FindingSeverity,
    StructuredAnalysisFindings,
)
from enhanced_finding_explanations import explain_analysis_findings


class FollowUpInspection(str, Enum):
    """Review requirements, never claims that inspection was performed."""

    validateStructure = "validateStructure"
    inspectObjectRelationships = "inspectObjectRelationships"
    inspectRevisionHistory = "inspectRevisionHistory"
    inspectActiveActions = "inspectActiveActions"
    inspectEmbeddedUrls = "inspectEmbeddedUrls"
    inspectEmbeddedFiles = "inspectEmbeddedFiles"
    inspectEmbeddedExecutables = "inspectEmbeddedExecutables"
    reviewUnsupportedFeature = "reviewUnsupportedFeature"
    reviewResourceLimits = "reviewResourceLimits"
    retryFailedInspection = "retryFailedInspection"
    retryIncompleteStage = "retryIncompleteStage"


# Explicit, complete policy table. None of these checks are invoked here.
# Run/review requirements remain unresolved even if an earlier discovery
# stage happened to have the same name: that stage may be the finding's origin.
_RULES = MappingProxyType({
    FindingCode.malformedStructure: (
        FollowUpInspection.validateStructure,
        FollowUpInspection.inspectObjectRelationships,
    ),
    FindingCode.conflictingStructure: (
        FollowUpInspection.inspectObjectRelationships,
        FollowUpInspection.inspectRevisionHistory,
    ),
    FindingCode.unresolvedReference: (
        FollowUpInspection.inspectObjectRelationships,
    ),
    # Confirmed malicious content is terminal blocking evidence; no further
    # inspection can turn this policy response into an opening authorization.
    FindingCode.knownMaliciousContent: (),
    FindingCode.activeContent: (
        FollowUpInspection.inspectActiveActions,
    ),
    FindingCode.suspiciousUrl: (
        FollowUpInspection.inspectEmbeddedUrls,
    ),
    FindingCode.unexpectedEmbeddedFile: (
        FollowUpInspection.inspectEmbeddedFiles,
        FollowUpInspection.inspectEmbeddedExecutables,
    ),
    FindingCode.incrementalRevision: (
        FollowUpInspection.inspectRevisionHistory,
    ),
    FindingCode.unsupportedFeature: (
        FollowUpInspection.reviewUnsupportedFeature,
    ),
    FindingCode.resourceLimit: (
        FollowUpInspection.reviewResourceLimits,
        FollowUpInspection.retryFailedInspection,
    ),
    FindingCode.inspectionFailure: (
        FollowUpInspection.retryFailedInspection,
    ),
})

if set(_RULES) != set(FindingCode):
    raise RuntimeError("Every structured finding code needs an explicit follow-up policy")


def _required_for(finding: AnalysisFinding) -> tuple[FollowUpInspection, ...]:
    if type(finding) is not AnalysisFinding:
        raise TypeError("Follow-up policy requires a validated AnalysisFinding")
    # An ordinary informational revision is not itself suspicious. Suspicious
    # and critical revisions still require inspection of prior revisions.
    if (finding.code is FindingCode.incrementalRevision and
            finding.severity is FindingSeverity.informational):
        return ()
    return _RULES[finding.code]


@dataclass(frozen=True)
class FindingInspectionRequirement:
    """Preserve the originating finding and its precise inspection needs."""

    source_stage: AnalysisStage
    finding: AnalysisFinding
    required_inspections: tuple[FollowUpInspection, ...] = field(init=False)

    def __post_init__(self):
        if type(self.source_stage) is not AnalysisStage:
            raise TypeError("Finding origin must be a validated stage")
        object.__setattr__(self, "required_inspections", _required_for(self.finding))

    @property
    def requires_additional_inspection(self) -> bool:
        return bool(self.required_inspections)

    def to_dict(self) -> dict:
        return {
            "sourceStage": self.source_stage.value,
            **self.finding.to_dict(),
            "requiresAdditionalInspection": self.requires_additional_inspection,
            "requiredInspections": [check.value for check in self.required_inspections],
        }


@dataclass(frozen=True)
class AdditionalInspectionPlan:
    """An immutable plan, not an executor, audit of completion or clean verdict.

    Required checks cannot be discharged merely because a source stage is
    marked completed. A distinct, reviewed execution contract is required.
    """

    source: StructuredAnalysisFindings
    finding_requirements: tuple[FindingInspectionRequirement, ...] = field(init=False)

    def __post_init__(self):
        if type(self.source) is not StructuredAnalysisFindings:
            raise TypeError("Expected a validated structured analysis report")
        by_stage = {stage.stage: stage for stage in self.source.stages}
        entries = tuple(
            FindingInspectionRequirement(stage, finding)
            for stage in self.source.expected_stages
            if stage in by_stage
            for finding in by_stage[stage].findings
        )
        object.__setattr__(self, "finding_requirements", entries)

    @property
    def incomplete_stages(self) -> tuple[AnalysisStage, ...]:
        return self.source.incomplete_stages

    @property
    def required_inspections(self) -> tuple[FollowUpInspection, ...]:
        # Fixed order independent of input ordering and duplicate findings.
        needed = {check for item in self.finding_requirements
                  for check in item.required_inspections}
        if self.incomplete_stages:
            needed.add(FollowUpInspection.retryIncompleteStage)
        return tuple(check for check in FollowUpInspection if check in needed)

    @property
    def requires_additional_inspection(self) -> bool:
        return bool(self.required_inspections)

    @property
    def requires_block(self) -> bool:
        # Existing explainable findings can already require blocking; add
        # outstanding work without downgrading any previous result.
        return (explain_analysis_findings(self.source).requires_block or
                self.requires_additional_inspection)

    @property
    def authorizes_open(self) -> bool:
        return False

    def to_dict(self) -> dict:
        return {
            "schemaVersion": 1,
            "authorizesOpen": False,
            "requiresBlock": self.requires_block,
            "requiresAdditionalInspection": self.requires_additional_inspection,
            "requiredInspections": [check.value for check in self.required_inspections],
            "incompleteStages": [stage.value for stage in self.incomplete_stages],
            "findingRequirements": [item.to_dict() for item in self.finding_requirements],
        }


def plan_additional_inspections(
    report: StructuredAnalysisFindings,
) -> AdditionalInspectionPlan:
    """Determine required follow-ups; never run a scanner or authorize opening."""
    return AdditionalInspectionPlan(report)
