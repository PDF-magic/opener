"""Measure additional Enhanced PDF inspection time without affecting scan decisions.

This optional observer does not activate Enhanced, enforce timeouts, or alter the
installed Built-in malware scanner, quarantine, cache, or application handoff.
"""

from dataclasses import dataclass
import time

from enhanced_analysis_findings import (
    AnalysisStage, MAX_REPORTED_STAGES, StageAnalysis, StageOutcome,
)

MAX_ELAPSED_NS = 2**63 - 1
TIMING_SCHEMA_VERSION = 1
BLOCK_MESSAGE = "Additional PDF analysis time could not be measured reliably."


class AdditionalAnalysisTimingError(RuntimeError):
    """Fixed path-free failure for untrustworthy timing evidence."""


def _check_expected(stages):
    if (type(stages) is not tuple or not 0 < len(stages) <= MAX_REPORTED_STAGES
            or any(type(item) is not AnalysisStage for item in stages)
            or len(stages) != len(set(stages))):
        raise ValueError("Expected analysis stages must be distinct trusted identifiers")


@dataclass(frozen=True)
class StageTiming:
    stage: AnalysisStage
    outcome: StageOutcome
    elapsed_nanoseconds: int

    def __post_init__(self):
        if type(self.stage) is not AnalysisStage or type(self.outcome) is not StageOutcome:
            raise TypeError("Timing requires validated stage and outcome identifiers")
        if (type(self.elapsed_nanoseconds) is not int or
                not 0 <= self.elapsed_nanoseconds <= MAX_ELAPSED_NS):
            raise ValueError("Elapsed analysis time must be a bounded integer")

    def to_dict(self):
        return {"stage": self.stage.value, "outcome": self.outcome.value,
                "elapsedNanoseconds": self.elapsed_nanoseconds}


@dataclass(frozen=True)
class AdditionalAnalysisTiming:
    """Immutable evidence, never a PDF safety or opening verdict."""

    expected_stages: tuple[AnalysisStage, ...]
    stages: tuple[StageTiming, ...] = ()

    def __post_init__(self):
        _check_expected(self.expected_stages)
        if type(self.stages) is not tuple or any(type(x) is not StageTiming for x in self.stages):
            raise ValueError("Timing records must be immutable and validated")
        actual = tuple(x.stage for x in self.stages)
        if (len(actual) != len(set(actual)) or
                actual != tuple(x for x in self.expected_stages if x in actual) or
                sum(x.elapsed_nanoseconds for x in self.stages) > MAX_ELAPSED_NS):
            raise ValueError("Timings must be unique, ordered, bounded and expected")

    @property
    def additional_nanoseconds(self):
        """Sum of explicitly measured extra work; excludes baseline and idle gaps."""
        return sum(x.elapsed_nanoseconds for x in self.stages)

    @property
    def timing_complete(self):
        return (len(self.stages) == len(self.expected_stages) and
                all(x.outcome is StageOutcome.completed for x in self.stages))

    @property
    def authorizes_open(self):
        return False

    def to_dict(self):
        found = {x.stage: x for x in self.stages}
        return {
            "schemaVersion": TIMING_SCHEMA_VERSION,
            "additionalAnalysisNanoseconds": self.additional_nanoseconds,
            "timingComplete": self.timing_complete,
            "authorizesOpen": False,
            "stageTimings": [
                found[x].to_dict() if x in found else {
                    "stage": x.value, "outcome": "notRun", "elapsedNanoseconds": None,
                }
                for x in self.expected_stages
            ],
        }


class AdditionalAnalysisTimer:
    """Wrap non-overlapping Enhanced stage work; retain original results/errors."""

    def __init__(self, expected_stages, *, clock=None):
        _check_expected(expected_stages)
        if clock is not None and not callable(clock):
            raise TypeError("Clock must be callable")
        self._expected = expected_stages
        self._clock = time.monotonic_ns if clock is None else clock
        self._last_tick = None
        self._recorded = {}
        self._active = False

    def _tick(self):
        try:
            now = self._clock()
        except Exception as exc:
            raise AdditionalAnalysisTimingError(BLOCK_MESSAGE) from exc
        if (type(now) is not int or not 0 <= now <= MAX_ELAPSED_NS or
                (self._last_tick is not None and now < self._last_tick)):
            raise AdditionalAnalysisTimingError(BLOCK_MESSAGE)
        self._last_tick = now
        return now

    def _finish(self, stage, started, outcome):
        elapsed = self._tick() - started
        self._recorded[stage] = StageTiming(stage, outcome, elapsed)

    def measure(self, stage, work):
        """Measure one matching StageAnalysis; never turn failures into clean results."""
        if (type(stage) is not AnalysisStage or stage not in self._expected or
                stage in self._recorded or self._active):
            raise ValueError("Measurement must be expected, unique and non-overlapping")
        if not callable(work):
            raise TypeError("Analysis work must be callable")
        started = self._tick()
        self._active = True
        try:
            try:
                result = work()
            except BaseException:
                self._finish(stage, started, StageOutcome.incomplete)
                raise
            if type(result) is not StageAnalysis or result.stage is not stage:
                self._finish(stage, started, StageOutcome.incomplete)
                raise TypeError("Analysis must return its matching structured stage result")
            self._finish(stage, started, result.outcome)
            return result
        finally:
            self._active = False

    def snapshot(self):
        if self._active:
            raise AdditionalAnalysisTimingError(BLOCK_MESSAGE)
        return AdditionalAnalysisTiming(
            self._expected,
            tuple(self._recorded[x] for x in self._expected if x in self._recorded),
        )
