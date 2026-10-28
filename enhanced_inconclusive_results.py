"""Fail-closed treatment of inconclusive *planned* Enhanced PDF evidence.

This is an analysis decision, never a clean scan result or permission to open.
Only a trusted policy may declare which inspection stages are expected.
No files are read, PDFs parsed, scanners run, or user preferences modified.
"""

from dataclasses import dataclass, field
from enum import Enum

from enhanced_analysis_findings import (
    AnalysisStage, FindingCode, FindingSeverity, StageOutcome,
    StructuredAnalysisFindings, MAX_PAGE_NUMBER, MAX_PDF_OBJECT_NUMBER,
)
from enhanced_finding_explanations import explain_analysis_findings


class IncompleteStageReason(str, Enum):
    """A required, trusted expected inspection did not finish."""

    notRun = "notRun"
    incomplete = "incomplete"


class InconclusiveOpeningDecision(str, Enum):
    """No result is an affirmative authorization to open a PDF."""

    block = "block"
    noDecision = "noDecision"


# A low producer-supplied severity cannot turn uncertainty into completeness.
# Each recognized finding code is deliberately classified; new codes must be
# reviewed rather than silently gaining a permissive default. Informational
# revisions alone are the one routine observation that does not imply missing
# evidence; suspicious/critical revisions still block for review.
_UNRESOLVED_CODES = frozenset({
    FindingCode.malformedStructure,
    FindingCode.conflictingStructure,
    FindingCode.unresolvedReference,
    FindingCode.activeContent,
    FindingCode.suspiciousUrl,
    FindingCode.unexpectedEmbeddedFile,
    FindingCode.unsupportedFeature,
    FindingCode.resourceLimit,
    FindingCode.inspectionFailure,
})
_ROUTINE_CODES = frozenset({FindingCode.incrementalRevision})
if (_UNRESOLVED_CODES & _ROUTINE_CODES or
        _UNRESOLVED_CODES | _ROUTINE_CODES != frozenset(FindingCode)):
    raise RuntimeError("Every finding code needs an explicit inconclusive policy")


@dataclass(frozen=True)
class InconclusiveEvidence:
    """Typed, path-free reason tied to one expected stage or PDF location."""

    stage: AnalysisStage
    reason: IncompleteStageReason | FindingCode
    object_number: int | None = None
    page_number: int | None = None

    def __post_init__(self):
        if type(self.stage) is not AnalysisStage:
            raise TypeError("Inconclusive evidence requires a validated stage")
        if type(self.reason) not in (IncompleteStageReason, FindingCode):
            raise TypeError("Inconclusive evidence requires a fixed reason")
        if (type(self.reason) is FindingCode and
                self.reason not in _UNRESOLVED_CODES | _ROUTINE_CODES):
            raise ValueError("Unknown finding reason")
        if (type(self.reason) is IncompleteStageReason and
                (self.object_number is not None or self.page_number is not None)):
            raise ValueError("Incomplete-stage reasons cannot claim PDF locations")
        for number, upper in ((self.object_number, MAX_PDF_OBJECT_NUMBER),
                              (self.page_number, MAX_PAGE_NUMBER)):
            if number is not None and (
                type(number) is not int or not 1 <= number <= upper
            ):
                raise ValueError("Evidence location must be a bounded integer")

    def to_dict(self) -> dict:
        return {
            "stage": self.stage.value,
            "reason": self.reason.value,
            "objectNumber": self.object_number,
            "pageNumber": self.page_number,
        }


@dataclass(frozen=True)
class InconclusiveOpeningAssessment:
    """Conservatively block unresolved evidence; never return a clean verdict.

    This policy preserves all preexisting analysis block signals. Even when
    this assessment does not block, mandatory baseline and remaining Enhanced
    checks are unverified, so opening is not authorized.
    """

    source: StructuredAnalysisFindings
    evidence: tuple[InconclusiveEvidence, ...] = field(init=False)
    requires_block: bool = field(init=False)

    def __post_init__(self):
        if type(self.source) is not StructuredAnalysisFindings:
            raise TypeError("Expected validated structured Enhanced findings")

        by_stage = {result.stage: result for result in self.source.stages}
        evidence = []
        for stage in self.source.expected_stages:
            result = by_stage.get(stage)
            if result is None:
                evidence.append(InconclusiveEvidence(
                    stage, IncompleteStageReason.notRun))
                continue
            if result.outcome is StageOutcome.incomplete:
                evidence.append(InconclusiveEvidence(
                    stage, IncompleteStageReason.incomplete))
            for finding in result.findings:
                if (finding.code in _UNRESOLVED_CODES or
                        (finding.code is FindingCode.incrementalRevision and
                         finding.severity is not FindingSeverity.informational)):
                    evidence.append(InconclusiveEvidence(
                        stage, finding.code, finding.object_number, finding.page_number))

        # The existing reporting/explanation gates can be stricter. Never
        # downgrade their block decisions or infer a pass from their absence.
        old_block = (self.source.requires_block or
                     explain_analysis_findings(self.source).requires_block)
        object.__setattr__(self, "evidence", tuple(evidence))
        object.__setattr__(self, "requires_block", bool(evidence) or old_block)

    @property
    def blocks_for_inconclusive(self) -> bool:
        return bool(self.evidence)

    @property
    def decision(self) -> InconclusiveOpeningDecision:
        return (InconclusiveOpeningDecision.block if self.requires_block
                else InconclusiveOpeningDecision.noDecision)

    @property
    def authorizes_open(self) -> bool:
        return False

    def to_dict(self) -> dict:
        return {
            "schemaVersion": 1,
            "decision": self.decision.value,
            "blocksForInconclusive": self.blocks_for_inconclusive,
            "requiresBlock": self.requires_block,
            "authorizesOpen": False,
            "evidence": [item.to_dict() for item in self.evidence],
        }


def assess_inconclusive_opening(
    report: StructuredAnalysisFindings,
) -> InconclusiveOpeningAssessment:
    """Compute opening-block requirements without inspecting or opening files."""
    return InconclusiveOpeningAssessment(report)
