"""Canonical terminal outcomes for a PDF Magic Opener scan request.

These outcomes describe what happened, not a guarantee that a file is safe.
Only "clean" authorizes proceeding to the existing open/quarantine gate.
Defining the vocabulary does not change how the current scanner runs or
assign outcomes to requests; integration belongs to separate checklist work.
"""

from enum import Enum


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
