"""Combine ClamAV outcomes and structural PDF findings without authorizing opening."""

from dataclasses import dataclass
import re

from enhanced_analysis_findings import StructuredAnalysisFindings
from enhanced_finding_explanations import explain_analysis_findings
from scan_results import ScanResult, ScanResultStatus


MAX_CLAMAV_DETECTION_NAMES = 256
# Match the fixed signature-name grammar in scan_results.py. Never serialize
# raw ClamAV lines, source paths, diagnostics, or PDF-controlled text.
_DETECTION_NAME = re.compile(r"[A-Za-z0-9][A-Za-z0-9._!+@-]{0,254}")


@dataclass(frozen=True)
class CombinedScanReport:
    """Immutable evidence from the scan gate and structural analysis.

    A clean ClamAV status does not override structural findings, and structural
    findings never override a ClamAV detection or failed scan. This report is
    evidence only: it never grants permission to open a document.
    """

    scan_status: ScanResultStatus
    clamav_result: ScanResult
    structural_findings: StructuredAnalysisFindings

    def __post_init__(self) -> None:
        if type(self.scan_status) is not ScanResultStatus:
            raise TypeError("A validated scan status is required")
        if type(self.clamav_result) is not ScanResult:
            raise TypeError("A validated ClamAV result is required")
        if type(self.structural_findings) is not StructuredAnalysisFindings:
            raise TypeError("Validated structured PDF findings are required")

        names = self.clamav_result.detection_names
        if type(names) is not tuple or len(names) > MAX_CLAMAV_DETECTION_NAMES:
            raise ValueError("ClamAV detection names must be a bounded immutable tuple")
        if any(type(name) is not str or _DETECTION_NAME.fullmatch(name) is None
               for name in names):
            raise ValueError("ClamAV detection names must be fixed signature identifiers")
        if len(set(names)) != len(names):
            raise ValueError("ClamAV detection names must be unique")
        if self.scan_status is ScanResultStatus.clean and names:
            raise ValueError("A clean scan status cannot contain ClamAV detections")

    @property
    def requires_block(self) -> bool:
        """Combine scan and structural signals conservatively."""
        structural = explain_analysis_findings(self.structural_findings)
        return (
            not self.scan_status.permits_open
            or bool(self.clamav_result.detection_names)
            or structural.requires_block
        )

    @property
    def authorizes_open(self) -> bool:
        """Combined evidence never substitutes for the existing opening gate."""
        return False

    def to_dict(self) -> dict:
        """Return detached, path-free combined evidence with stable field names."""
        structural = explain_analysis_findings(self.structural_findings)
        return {
            "schemaVersion": 1,
            "authorizesOpen": False,
            "requiresBlock": (
                not self.scan_status.permits_open
                or bool(self.clamav_result.detection_names)
                or structural.requires_block
            ),
            "scan": {
                "status": self.scan_status.value,
            },
            "clamav": {
                "effectivePolicyId": self.clamav_result.effective_policy_id,
                "detectionNames": list(self.clamav_result.detection_names),
            },
            "structuralFindings": structural.to_dict(),
        }


def combine_scan_results(
    scan_status: ScanResultStatus,
    clamav_result: ScanResult,
    structural_findings: StructuredAnalysisFindings,
) -> CombinedScanReport:
    """Combine independently validated scan and structural evidence.

    The result remains non-authorizing. Callers must continue to enforce the
    installed ClamAV, quarantine, integrity and verified-handoff checks.
    """
    return CombinedScanReport(scan_status, clamav_result, structural_findings)
