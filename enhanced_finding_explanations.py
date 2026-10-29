"""Explain every structured Enhanced PDF finding without changing its evidence.

This adapter adds stable, path-free explanations and handling results to the
structured reporting contract from opener-0297. It does not parse PDFs, make
opening decisions, or modify the installed scanner (opener-0299).
"""

from dataclasses import dataclass, field
from enum import Enum
from types import MappingProxyType

from enhanced_analysis_findings import (
    AnalysisFinding, FindingCode, FindingSeverity, StructuredAnalysisFindings,
)


class FindingResult(str, Enum):
    """A finding's handling result, not a PDF clean/unsafe execution verdict."""

    recorded = "recorded"
    reviewRequired = "reviewRequired"
    blocking = "blocking"
    inspectionIncomplete = "inspectionIncomplete"


class FindingNextAction(str, Enum):
    """Safe, fixed guidance independent of document-provided text."""

    continueRequiredChecks = "continueRequiredChecks"
    requestReviewBeforeOpening = "requestReviewBeforeOpening"
    stopOpening = "stopOpening"
    rerunOrRepairInspection = "rerunOrRepairInspection"


# Never interpolate PDF-controlled URLs, filenames, objects, scripts, paths, or
# exception text into user-visible explanations.
_EXPLANATIONS = MappingProxyType({
    FindingCode.malformedStructure:
        "PDF structure is malformed; trustworthy interpretation requires validation.",
    FindingCode.conflictingStructure:
        "Conflicting PDF structures prevent an unambiguous interpretation.",
    FindingCode.unresolvedReference:
        "A referenced PDF object could not be resolved reliably.",
    FindingCode.activeContent:
        "A PDF active-content capability was found; this does not prove execution.",
    FindingCode.suspiciousUrl:
        "An embedded URL merits further inspection; no URL has been contacted.",
    FindingCode.unexpectedEmbeddedFile:
        "Embedded file content needs independent inspection before any opening decision.",
    FindingCode.incrementalRevision:
        "A PDF incremental revision was observed; earlier revisions may need review.",
    FindingCode.unsupportedFeature:
        "The inspection does not fully support a PDF feature; no safety conclusion follows.",
    FindingCode.resourceLimit:
        "Inspection exceeded a configured resource bound and could not finish reliably.",
    FindingCode.inspectionFailure:
        "Inspection did not establish complete evidence for this finding.",
})

# Incomplete analysis cannot be downgraded by a low producer-supplied severity.
_INCOMPLETE_CODES = frozenset((FindingCode.resourceLimit, FindingCode.inspectionFailure))
_HANDLING = MappingProxyType({
    FindingResult.recorded: FindingNextAction.continueRequiredChecks,
    FindingResult.reviewRequired: FindingNextAction.requestReviewBeforeOpening,
    FindingResult.blocking: FindingNextAction.stopOpening,
    FindingResult.inspectionIncomplete: FindingNextAction.rerunOrRepairInspection,
})


def _result_for(finding: AnalysisFinding) -> FindingResult:
    if type(finding) is not AnalysisFinding:
        raise TypeError("Expected a validated structured finding")
    if finding.code in _INCOMPLETE_CODES:
        return FindingResult.inspectionIncomplete
    if finding.severity in (FindingSeverity.blocking, FindingSeverity.critical):
        return FindingResult.blocking
    if finding.severity in (FindingSeverity.reviewRequired, FindingSeverity.suspicious):
        return FindingResult.reviewRequired
    return FindingResult.recorded


@dataclass(frozen=True)
class ExplainedFinding:
    """Immutable validated finding and a complete, explainable handling result."""

    finding: AnalysisFinding

    def __post_init__(self):
        if type(self.finding) is not AnalysisFinding:
            raise TypeError("Explanation needs a validated structured finding")
        if self.finding.code not in _EXPLANATIONS:
            raise ValueError("Every recognized finding code must have an explanation")

    @property
    def result(self) -> FindingResult:
        return _result_for(self.finding)

    @property
    def next_action(self) -> FindingNextAction:
        return _HANDLING[self.result]

    @property
    def explanation(self) -> str:
        return _EXPLANATIONS[self.finding.code]

    def to_dict(self) -> dict:
        return {
            **self.finding.to_dict(),
            "result": {
                "outcome": self.result.value,
                "explanation": self.explanation,
                "nextAction": self.next_action.value,
            },
        }


@dataclass(frozen=True)
class ExplainableAnalysisFindings:
    """Decorate all reported findings without omitting any stages or evidence.

    Expected stages are trusted policy input to the existing report. Its missing
    and incomplete stages remain visible; a fully explained report is still
    partial security evidence and NEVER authorizes opening.
    """

    source: StructuredAnalysisFindings
    stage_findings: tuple[tuple[ExplainedFinding, ...], ...] = field(init=False)

    def __post_init__(self):
        if type(self.source) is not StructuredAnalysisFindings:
            raise TypeError("Expected a complete structured-analysis report")
        found = {stage.stage: stage for stage in self.source.stages}
        explained = tuple(
            tuple(ExplainedFinding(finding) for finding in found[expected].findings)
            if expected in found else ()
            for expected in self.source.expected_stages
        )
        object.__setattr__(self, "stage_findings", explained)

    @property
    def requires_block(self) -> bool:
        # Preserve the base report's conservative result, and additionally
        # block a completed stage that mistakenly labels failure informational.
        return self.source.requires_block or any(
            finding.result is not FindingResult.recorded
            for stage in self.stage_findings for finding in stage
        )

    @property
    def authorizes_open(self) -> bool:
        return False

    def to_dict(self) -> dict:
        """JSON-ready v2 report with a result attached to EVERY input finding."""
        payload = self.source.to_dict()
        payload["schemaVersion"] = 2
        payload["authorizesOpen"] = False
        payload["requiresBlock"] = self.requires_block
        for stage, explained in zip(payload["stageResults"], self.stage_findings):
            # Stage order, counts, missing-stage status and locations are all
            # inherited from the v1 contract; never create a clean fallback.
            stage["findings"] = [finding.to_dict() for finding in explained]
        return payload


def explain_analysis_findings(
    report: StructuredAnalysisFindings,
) -> ExplainableAnalysisFindings:
    """Produce explainable evidence, not a PDF admission or safety decision."""
    return ExplainableAnalysisFindings(report)
