"""Canonical terminal outcomes for a PDF Magic Opener scan request.

These outcomes describe what happened, not a guarantee that a file is safe.
Only "clean" authorizes proceeding to the existing open/quarantine gate.
Defining the vocabulary does not change how the current scanner runs or
assign outcomes to requests; integration belongs to separate checklist work.
"""

from dataclasses import dataclass, field
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


# Only ordinary ClamAV signature identifiers belong in structured results.
# Exclude scanned paths, arbitrary diagnostics, and malformed FOUND lines.
# This is the *enforced* scan-gate policy, not a requested or persisted tier.
# Standard/Enhanced/Maximum exist only as inactive definitions.
EFFECTIVE_POLICY_ID = "built-in"


_DETECTION_NAME = re.compile(r"[A-Za-z0-9][A-Za-z0-9._!+@-]{0,254}\Z")


@dataclass(frozen=True)
class ScanResult:
    """In-memory result metadata; detection names never authorize opening."""

    detection_names: tuple[str, ...] = ()
    # Derived from the installed scan gate, never supplied by the caller.
    effective_policy_id: str = field(default=EFFECTIVE_POLICY_ID, init=False)

    @classmethod
    def from_clamav_output(cls, output):
        names = []
        for line in (output or "").splitlines():
            if not line.endswith(" FOUND"):
                continue
            source, separator, name = line[:-len(" FOUND")].rpartition(": ")
            if source and separator and _DETECTION_NAME.fullmatch(name) and name not in names:
                names.append(name)
        return cls(detection_names=tuple(names))
