"""Build honest performance summaries from completed, measured stage work.

No production scanner modifications. Only complete, genuine stage timing
snapshots may contribute to an optional illustrative benchmark report. These
figures measure additional instrumented inspection stages, NOT a full PDF
opening or an enforced protection tier.
"""
from dataclasses import dataclass
import json
import math
import statistics
from enhanced_analysis_timing import AdditionalAnalysisTiming
from protection_profiles import ProtectionProfileID

SCHEMA_VERSION = 1
SCOPE = "instrumentedAdditionalStages"
MIN_SAMPLES = 5
MAX_SAMPLES = 101
MAX_MILLISECONDS = 3_600_000


@dataclass(frozen=True)
class PerformanceSampleGroup:
    profile: ProtectionProfileID
    timings: tuple[AdditionalAnalysisTiming, ...]

    def __post_init__(self):
        if self.profile not in (ProtectionProfileID.ENHANCED, ProtectionProfileID.MAXIMUM):
            raise ValueError("Only instrumented additional inspection stages may be compared")
        if type(self.timings) is not tuple or not MIN_SAMPLES <= len(self.timings) <= MAX_SAMPLES:
            raise ValueError("Enough bounded independent timing samples are required")
        if any(type(t) is not AdditionalAnalysisTiming or not t.timing_complete
               for t in self.timings):
            raise ValueError("Failed or partial stage measurements cannot give an estimate")
        expected = self.timings[0].expected_stages
        if any(t.expected_stages != expected for t in self.timings):
            raise ValueError("Samples must measure the same inspection stages")
        if any(not 0 < t.additional_nanoseconds <= MAX_MILLISECONDS * 1_000_000
               for t in self.timings):
            raise ValueError("Zero or excessive elapsed timings are not representative")

    def to_dict(self):
        values = sorted(t.additional_nanoseconds / 1_000_000 for t in self.timings)
        midpoint = statistics.median(values)
        p90 = values[math.ceil(0.9 * len(values)) - 1]
        return {
            "profile": self.profile.value,
            "sampleCount": len(values),
            "medianAdditionalMilliseconds": round(midpoint, 3),
            "p90AdditionalMilliseconds": round(p90, 3),
        }


def build_report(*groups: PerformanceSampleGroup, platform: str, workload: str) -> dict:
    """Detached, privacy-safe measured stage timing data for the native UI.

    Caller must describe the exact platform/workload; neither is guessed.
    An empty set means no defensible numeric estimate is available.
    """
    if type(platform) is not str or not 3 <= len(platform) <= 90 or any(
        ch not in "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789 ._-()"
        for ch in platform
    ):
        raise ValueError("Provide a bounded non-sensitive platform description")
    if type(workload) is not str or not 3 <= len(workload) <= 100 or any(
        ch not in "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789 ._-()"
        for ch in workload
    ):
        raise ValueError("Provide a bounded non-sensitive workload description")
    if any(type(g) is not PerformanceSampleGroup for g in groups):
        raise ValueError("Only validated timing groups are allowed")
    if len(set(g.profile for g in groups)) != len(groups):
        raise ValueError("Each planned tier may appear once")
    return {
        "schemaVersion": SCHEMA_VERSION,
        "scope": SCOPE,
        "platform": platform,
        "workload": workload,
        "measurements": [g.to_dict() for g in groups],
    }


def encode_report(report: dict) -> bytes:
    """Return deterministic JSON after validating the generated report shape."""
    if type(report) is not dict or set(report) != {
        "schemaVersion", "scope", "platform", "workload", "measurements"
    }:
        raise ValueError("Unrecognized evidence structure")
    if report["schemaVersion"] != SCHEMA_VERSION or report["scope"] != SCOPE:
        raise ValueError("Unrecognized evidence schema or scope")
    # Reject caller-provided raw dictionaries without the guarded build step.
    return json.dumps(report, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")
