"""Concise, path-free document-security summaries for combined scan evidence."""

from collections import Counter
from dataclasses import dataclass

from combined_scan_results import CombinedScanReport
from enhanced_analysis_findings import FindingCode, FindingSeverity
from scan_results import ScanResultStatus


# Fixed, report-only classifications; never change the installed opening gate.
_WARNING_SCAN_STATUSES = frozenset({
    ScanResultStatus.suspiciousStructure,
    ScanResultStatus.encrypted,
    ScanResultStatus.fileTooLarge,
})
_SYSTEM_FAILURE_SCAN_STATUSES = frozenset({
    ScanResultStatus.incompleteScan,
    ScanResultStatus.scanFailed,
    ScanResultStatus.scanTimedOut,
})
_SYSTEM_FAILURE_CODES = frozenset({
    FindingCode.resourceLimit,
    FindingCode.inspectionFailure,
})

MAX_DISPLAYED_SIGNATURES = 3
MAX_SIGNATURE_LABEL_LENGTH = 64

_SCAN_STATUS_LABELS = {
    ScanResultStatus.suspiciousStructure: "Suspicious PDF structure",
    ScanResultStatus.encrypted: "Encrypted; required inspection unavailable",
    ScanResultStatus.incompleteScan: "Inspection incomplete",
    ScanResultStatus.scanFailed: "Scanner failure",
    ScanResultStatus.scanTimedOut: "Scan timed out",
    ScanResultStatus.fileChanged: "File changed during verification",
    ScanResultStatus.fileTooLarge: "File exceeded a scan limit",
    ScanResultStatus.cancelled: "Scan cancelled",
}

_FINDING_OUTCOME_ORDER = (
    ("blocking", "blocking"),
    ("inspectionIncomplete", "inspection incomplete"),
    ("reviewRequired", "review required"),
    ("recorded", "informational"),
)


def _plural(count: int, singular: str) -> str:
    return singular if count == 1 else singular + "s"


def _display_signature_name(name: str) -> str:
    if len(name) <= MAX_SIGNATURE_LABEL_LENGTH:
        return name
    return name[:MAX_SIGNATURE_LABEL_LENGTH - 3] + "..."


@dataclass(frozen=True)
class DocumentSecurityReport:
    """A short human-readable summary; never a file-opening authorization."""

    combined_scan_report: CombinedScanReport

    def __post_init__(self) -> None:
        if type(self.combined_scan_report) is not CombinedScanReport:
            raise TypeError("A validated combined scan report is required")

    @property
    def requires_block(self) -> bool:
        return self.combined_scan_report.requires_block

    @property
    def authorizes_open(self) -> bool:
        return False

    @property
    def issue_channels(self) -> dict:
        """Keep validated document warnings separate from inspection failures.

        Known malicious content stays in its own existing evidence category.
        No channel permits an open or overrides the conservative block result.
        """
        status = self.combined_scan_report.scan_status
        structural = self.combined_scan_report.structural_findings
        warning_count = 0
        failure_count = 0
        for stage in structural.stages:
            for finding in stage.findings:
                if finding.code in _SYSTEM_FAILURE_CODES:
                    failure_count += 1
                elif (finding.code is not FindingCode.knownMaliciousContent
                      and finding.severity is not FindingSeverity.informational):
                    warning_count += 1
        return {
            "warnings": {
                "scanStatus": status.value if status in _WARNING_SCAN_STATUSES else None,
                "structuralFindings": warning_count,
            },
            "systemFailures": {
                "scanStatus": status.value if status in _SYSTEM_FAILURE_SCAN_STATUSES else None,
                "incompleteStages": len(structural.incomplete_stages),
                "structuralFindings": failure_count,
            },
        }

    @property
    def warning_summary(self) -> str:
        warnings = self.issue_channels["warnings"]
        parts = []
        if warnings["scanStatus"] is not None:
            parts.append(_SCAN_STATUS_LABELS[ScanResultStatus(warnings["scanStatus"])])
        count = warnings["structuralFindings"]
        if count:
            parts.append(f"{count} structural review {_plural(count, 'finding')}")
        return "Warnings: " + ("; ".join(parts) if parts else "None reported") + "."

    @property
    def system_failure_summary(self) -> str:
        failures = self.issue_channels["systemFailures"]
        parts = []
        if failures["scanStatus"] is not None:
            parts.append(_SCAN_STATUS_LABELS[ScanResultStatus(failures["scanStatus"])])
        incomplete = failures["incompleteStages"]
        if incomplete:
            parts.append(f"{incomplete} incomplete inspection {_plural(incomplete, 'stage')}")
        count = failures["structuralFindings"]
        if count:
            parts.append(f"{count} inspection failure {_plural(count, 'finding')}")
        return "System failures: " + ("; ".join(parts) if parts else "None reported") + "."

    @property
    def headline(self) -> str:
        if self.requires_block:
            return "Document security: BLOCKED"
        return "Document security: No blocking findings reported"

    @property
    def scan_summary(self) -> str:
        status = self.combined_scan_report.scan_status
        names = self.combined_scan_report.clamav_result.detection_names

        if status is ScanResultStatus.clean:
            return "ClamAV: No malware signatures detected (Built-in policy)."

        if status is ScanResultStatus.malwareDetected:
            if not names:
                return (
                    "ClamAV: Malware detection reported; "
                    "signature details unavailable."
                )
            label = _plural(len(names), "signature")
            displayed = [
                _display_signature_name(name)
                for name in names[:MAX_DISPLAYED_SIGNATURES]
            ]
            if len(names) > MAX_DISPLAYED_SIGNATURES:
                displayed.append(f"+{len(names) - MAX_DISPLAYED_SIGNATURES} more")
            return (
                f"ClamAV: Malware detected ({len(names)} {label}: "
                f"{', '.join(displayed)})."
            )

        if names:
            displayed = [
                _display_signature_name(name)
                for name in names[:MAX_DISPLAYED_SIGNATURES]
            ]
            if len(names) > MAX_DISPLAYED_SIGNATURES:
                displayed.append(f"+{len(names) - MAX_DISPLAYED_SIGNATURES} more")
            label = _plural(len(names), "detection")
            return (
                f"ClamAV: {len(names)} {label} reported "
                f"({', '.join(displayed)}); "
                f"scan status: {_SCAN_STATUS_LABELS[status]}."
            )

        return f"Scan status: {_SCAN_STATUS_LABELS[status]}."

    @property
    def structural_summary(self) -> str:
        structural = self.combined_scan_report.to_dict()["structuralFindings"]
        stages = structural["stageResults"]
        incomplete_stages = sum(stage["outcome"] != "completed" for stage in stages)
        stage_word = _plural(len(stages), "stage")
        if incomplete_stages:
            stage_summary = (
                f"{incomplete_stages} of {len(stages)} {stage_word} incomplete"
            )
        else:
            stage_summary = f"{len(stages)} {stage_word} completed"

        findings = [
            finding
            for stage in stages
            for finding in stage["findings"]
        ]
        if not findings and not incomplete_stages:
            return (
                "Structural inspection: No findings reported across "
                f"{len(stages)} completed {stage_word}; this is not a clean verdict."
            )
        if not findings:
            return (
                "Structural inspection: No findings recorded; "
                f"{stage_summary}."
            )

        counts = Counter(
            finding["result"]["outcome"]
            for finding in findings
        )
        labels = [
            f"{counts[outcome]} {label}"
            for outcome, label in _FINDING_OUTCOME_ORDER
            if counts[outcome]
        ]
        finding_summary = (
            f"{len(findings)} {_plural(len(findings), 'finding')}"
            f" ({', '.join(labels)})"
        )
        return f"Structural inspection: {finding_summary}; {stage_summary}."

    @property
    def next_step(self) -> str:
        if self.requires_block:
            return "Next step: Keep the document blocked until flagged checks are resolved."
        return "Next step: Continue through the existing opening gate."

    def to_dict(self) -> dict:
        """Return a compact, detached summary using fixed field names."""
        return {
            "schemaVersion": 1,
            "authorizesOpen": False,
            "requiresBlock": self.requires_block,
            "headline": self.headline,
            "scanSummary": self.scan_summary,
            "structuralSummary": self.structural_summary,
            "warnings": self.issue_channels["warnings"],
            "systemFailures": self.issue_channels["systemFailures"],
            "nextStep": self.next_step,
        }

    def to_text(self) -> str:
        """Render the concise report without paths or document-controlled text."""
        return "\n".join((
            self.headline,
            self.scan_summary,
            self.structural_summary,
            self.warning_summary,
            self.system_failure_summary,
            self.next_step,
            "Opening authorization: Not granted by this report.",
        ))


def create_document_security_report(
    combined_scan_report: CombinedScanReport,
) -> DocumentSecurityReport:
    """Render concise, path-free findings without changing the existing scan gate."""
    return DocumentSecurityReport(combined_scan_report)
