"""Canonical terminal outcomes for a PDF Magic Opener scan request.

These outcomes describe what happened, not a guarantee that a file is safe.
Only "clean" authorizes proceeding to the existing open/quarantine gate.
Defining the vocabulary does not change how the current scanner runs or
assign outcomes to requests; integration belongs to separate checklist work.
"""

from dataclasses import dataclass
from enum import Enum
import re


class ScanResultStatus(str, Enum):
    """Stable, JSON-compatible names for completed or stopped scan requests."""

    clean = "clean"  # Required checks completed without detected issues.
    malwareDetected = "malwareDetected"  # Malware detection by the scan engine.
    suspiciousStructure = "suspiciousStructure"  # Suspicious/malformed structure.
    encrypted = "encrypted"  # Encryption prevented required inspection.
    incompleteScan = "incompleteScan"  # Required inspection was skipped/partial.
    scanFailed = "scanFailed"  # Scanner or prerequisite failed unexpectedly.
    scanTimedOut = "scanTimedOut"  # The scan exceeded its allotted time.
    fileChanged = "fileChanged"  # Input content changed during verification.
    fileTooLarge = "fileTooLarge"  # Configured/engine size limit was exceeded.
    cancelled = "cancelled"  # The request was explicitly cancelled.

    @property
    def permits_open(self):
        """Only a confirmed clean verdict permits subsequent open processing."""
        return self is ScanResultStatus.clean


# ClamAV writes "<scanned path>: <signature> FOUND" for positive matches.
# Only record conventional signature identifiers, never scanned paths or
# arbitrary scanner diagnostic text in result metadata.
_DETECTION_NAME = re.compile(r"[A-Za-z0-9][A-Za-z0-9._!+@-]{0,254}\Z")


@dataclass(frozen=True)
class ScanResult:
    """In-memory detection metadata; not itself proof that a scan is clean."""

    detection_names: tuple[str, ...] = ()

    @classmethod
    def from_clamav_output(cls, output):
        """Extract unique ClamAV signature names in first-seen order."""
        names = []
        for line in output.splitlines():
            if not line.endswith(" FOUND"):
                continue
            source, separator, signature = line[:-len(" FOUND")].rpartition(": ")
            if not source or not separator or not _DETECTION_NAME.fullmatch(signature):
                continue
            if signature not in names:
                names.append(signature)
        return cls(detection_names=tuple(names))
