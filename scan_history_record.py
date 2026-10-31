"""Passive, versioned metadata format for future opt-in local scan history.

No history is captured or persisted here. Only the trusted scan coordinator
may create records; a saved verdict never authorizes opening a document.
"""

from dataclasses import dataclass, field
from enum import Enum
import unicodedata

from scan_results import ScanResultStatus


HISTORY_SCHEMA_VERSION = 1
_MAX_TIMESTAMP = (1 << 53) - 1  # Safe integer in JSON consumers.


class ScanHistorySource(str, Enum):
    finder = "finder"
    browser = "browser"
    desktopApplication = "desktop-application"
    commandLine = "command-line"
    unknown = "unknown"


def _valid_basename(name):
    return (
        name not in ("", ".", "..")
        and len(name) <= 255
        and not any(ch in "/\\" or unicodedata.category(ch) in ("Cc", "Cf") for ch in name)
    )


@dataclass(frozen=True)
class ScanHistoryRecord:
    """One completed request; missing opening evidence is *not* success.

    ``filename`` is optional and, if provided by a trusted local caller, must
    be a basename. Never include full paths, URLs, diagnostic text, or PDF data.
    """

    timestamp: int  # UTC Unix seconds, not a local wall-clock timestamp.
    status: ScanResultStatus
    source: ScanHistorySource = ScanHistorySource.unknown
    filename: str | None = None
    opened: bool | None = None  # None: not verified; never infer from "clean".
    schema_version: int = field(default=HISTORY_SCHEMA_VERSION, init=False)

    def __post_init__(self):
        if type(self.timestamp) is not int or not 0 <= self.timestamp <= _MAX_TIMESTAMP:
            raise ValueError("timestamp must be a nonnegative JSON-safe UTC second")
        if not isinstance(self.status, ScanResultStatus):
            raise ValueError("status must be a canonical scan result")
        if not isinstance(self.source, ScanHistorySource):
            raise ValueError("source must be a recognized scan origin")
        if self.filename is not None and (
            type(self.filename) is not str or not _valid_basename(self.filename)
        ):
            raise ValueError("filename must be a safe basename or None")
        if self.opened is not None and type(self.opened) is not bool:
            raise ValueError("opened must be a verified boolean or None")

    def to_dict(self):
        """Return only the six allowlisted JSON-compatible metadata fields."""
        return {
            "schema_version": self.schema_version,
            "timestamp": self.timestamp,
            "status": self.status.value,
            "source": self.source.value,
            "filename": self.filename,
            "opened": self.opened,
        }

    @classmethod
    def from_dict(cls, value):
        """Reject unsupported versions, unrecognized fields, and bad values."""
        if not isinstance(value, dict) or set(value) != {
            "schema_version", "timestamp", "status", "source", "filename", "opened"
        }:
            raise ValueError("invalid history record fields")
        if type(value["schema_version"]) is not int or value["schema_version"] != HISTORY_SCHEMA_VERSION:
            raise ValueError("unsupported history schema version")
        if type(value["status"]) is not str or type(value["source"]) is not str:
            raise ValueError("status and source must be strings")
        try:
            status = ScanResultStatus(value["status"])
            source = ScanHistorySource(value["source"])
        except ValueError as exc:
            raise ValueError("unknown scan status or source") from exc
        return cls(
            timestamp=value["timestamp"], status=status, source=source,
            filename=value["filename"], opened=value["opened"],
        )
