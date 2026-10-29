"""Structured, path-free evidence for future Enhanced PDF inspections.

This is a reporting contract, not a parser, a scanner, or a PDF clean verdict.
It does not enable Enhanced protection, bypass ClamAV, change preferences, or
authorize a file to open. Only trusted inspector code may select identifiers;
PDF-controlled strings, decoded content, paths, and exception text are excluded.
"""

from dataclasses import dataclass
from enum import Enum


MAX_REPORTED_STAGES = 32
MAX_FINDINGS_PER_STAGE = 128
MAX_PDF_OBJECT_NUMBER = 2**31 - 1
MAX_PAGE_NUMBER = 1_000_000
FINDING_IDENTIFIER_VERSION = 1


class AnalysisStage(str, Enum):
    """Known Enhanced inspection components; not evidence they have run."""

    pdfStructure = "pdfStructure"
    objectRelationships = "objectRelationships"
    embeddedFiles = "embeddedFiles"
    automaticActions = "automaticActions"
    javascriptActions = "javascriptActions"
    formActions = "formActions"
    annotations = "annotations"
    incrementalRevisions = "incrementalRevisions"
    embeddedUrls = "embeddedUrls"
    malformedStructures = "malformedStructures"
    ambiguousStructures = "ambiguousStructures"
    executableContent = "executableContent"


class FindingCode(str, Enum):
    """Fixed diagnostic codes, never arbitrary PDF-supplied descriptions."""

    malformedStructure = "malformedStructure"
    conflictingStructure = "conflictingStructure"
    unresolvedReference = "unresolvedReference"
    activeContent = "activeContent"
    suspiciousUrl = "suspiciousUrl"
    unexpectedEmbeddedFile = "unexpectedEmbeddedFile"
    incrementalRevision = "incrementalRevision"
    unsupportedFeature = "unsupportedFeature"
    resourceLimit = "resourceLimit"
    inspectionFailure = "inspectionFailure"


class FindingSeverity(str, Enum):
    """Conservative classification of a finding, not an opening authorization."""

    informational = "informational"
    reviewRequired = "reviewRequired"
    suspicious = "suspicious"
    critical = "critical"
    blocking = "blocking"


class StageOutcome(str, Enum):
    completed = "completed"
    incomplete = "incomplete"


@dataclass(frozen=True)
class AnalysisFinding:
    """Bounded evidence without filenames, source URLs, text, or payloads."""

    code: FindingCode
    severity: FindingSeverity
    object_number: int | None = None
    page_number: int | None = None

    def __post_init__(self):
        if type(self.code) is not FindingCode or type(self.severity) is not FindingSeverity:
            raise TypeError("Finding identifiers and severity must be validated enums")
        for value, upper in ((self.object_number, MAX_PDF_OBJECT_NUMBER),
                             (self.page_number, MAX_PAGE_NUMBER)):
            if value is not None and (type(value) is not int or not 1 <= value <= upper):
                raise ValueError("Finding locations must be bounded positive integers")

    @property
    def finding_id(self) -> str:
        """Stable evidence-signature ID, independent of severity or run order.

        The identifier is scoped by code and the available object/page location,
        not by document identity. Identical signatures intentionally share an ID.
        """
        object_number = "none" if self.object_number is None else str(self.object_number)
        page_number = "none" if self.page_number is None else str(self.page_number)
        return (
            f"finding-v{FINDING_IDENTIFIER_VERSION}:{self.code.value}:"
            f"object={object_number}:page={page_number}"
        )

    def to_dict(self):
        return {
            "code": self.code.value,
            "findingId": self.finding_id,
            "severity": self.severity.value,
            "objectNumber": self.object_number,
            "pageNumber": self.page_number,
        }


@dataclass(frozen=True)
class StageAnalysis:
    """An inspection stage may be incomplete even after collecting evidence."""

    stage: AnalysisStage
    outcome: StageOutcome
    findings: tuple[AnalysisFinding, ...] = ()

    def __post_init__(self):
        if type(self.stage) is not AnalysisStage or type(self.outcome) is not StageOutcome:
            raise TypeError("Stage and outcome must be validated enums")
        if type(self.findings) is not tuple or len(self.findings) > MAX_FINDINGS_PER_STAGE:
            raise ValueError("Stage findings must be a bounded immutable tuple")
        if any(type(finding) is not AnalysisFinding for finding in self.findings):
            raise TypeError("Every finding must be a validated AnalysisFinding")

    def to_dict(self):
        return {
            "stage": self.stage.value,
            "outcome": self.outcome.value,
            "findings": [finding.to_dict() for finding in self.findings],
        }


@dataclass(frozen=True)
class StructuredAnalysisFindings:
    """Report expected stages explicitly, including missing and failed ones.

    The expected stages must come from trusted caller policy, not a PDF. A
    report is scoped to these stages only, and NEVER implies the remaining
    required baseline or Enhanced inspections were performed.
    """

    expected_stages: tuple[AnalysisStage, ...]
    stages: tuple[StageAnalysis, ...] = ()

    def __post_init__(self):
        if (type(self.expected_stages) is not tuple or not self.expected_stages or
                len(self.expected_stages) > MAX_REPORTED_STAGES or
                any(type(stage) is not AnalysisStage for stage in self.expected_stages) or
                len(set(self.expected_stages)) != len(self.expected_stages)):
            raise ValueError("Expected stages must be distinct known stage identifiers")
        if (type(self.stages) is not tuple or len(self.stages) > len(self.expected_stages) or
                any(type(stage) is not StageAnalysis for stage in self.stages)):
            raise ValueError("Stage results must be a bounded immutable tuple")
        reported = [stage.stage for stage in self.stages]
        if len(set(reported)) != len(reported) or not set(reported).issubset(self.expected_stages):
            raise ValueError("Stage results must be unique and expected")

    @property
    def incomplete_stages(self):
        reported = {result.stage: result for result in self.stages}
        return tuple(stage for stage in self.expected_stages
                     if stage not in reported or reported[stage].outcome is StageOutcome.incomplete)

    @property
    def requires_block(self):
        """Conservative analysis signal, not an independent opening decision."""
        return bool(self.incomplete_stages or any(
            finding.severity is not FindingSeverity.informational
            for result in self.stages for finding in result.findings
        ))

    def to_dict(self):
        """Detached, JSON-serializable data in stable expected-stage order."""
        reported = {result.stage: result for result in self.stages}
        return {
            "schemaVersion": 1,
            "authorizesOpen": False,
            "requiresBlock": self.requires_block,
            "stageResults": [
                reported[stage].to_dict() if stage in reported else {
                    "stage": stage.value, "outcome": "notRun", "findings": [],
                }
                for stage in self.expected_stages
            ],
        }
