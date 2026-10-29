# Measuring additional Enhanced analysis time (opener-0304)

The optional `enhanced_analysis_timing.AdditionalAnalysisTimer` measures only
the extra work performed by individually instrumented, planned Enhanced PDF
inspection stages. It uses `time.monotonic_ns()` and accepts trusted
`AnalysisStage` identifiers, with start/end boundaries around each callback.
Each callback returns the original matching `StageAnalysis`; the timer does
not modify the result or swallow errors.

```python
from enhanced_analysis_findings import AnalysisStage, StageAnalysis, StageOutcome
from enhanced_analysis_timing import AdditionalAnalysisTimer

timer = AdditionalAnalysisTimer((AnalysisStage.pdfStructure,))
result = timer.measure(
    AnalysisStage.pdfStructure,
    lambda: StageAnalysis(AnalysisStage.pdfStructure, StageOutcome.completed),
)
report = timer.snapshot().to_dict()
assert report["stageTimings"][0]["elapsedNanoseconds"] >= 0
assert report["authorizesOpen"] is False
```

`additionalAnalysisNanoseconds` is the **sum of per-stage measured elapsed
nanoseconds**, excluding gaps between the calls and baseline ClamAV operations.
This is not a claim about end-to-end PDF opening latency. A missing stage is
reported as `notRun` with no fabricated duration; incomplete stages and
failed or cancelled attempts cannot produce `timingComplete=True`.
Unexpected, repeated, or overlapping stages and invalid or reversing clock
readings fail closed. Exception messages, PDF content, paths, URLs and
filenames are never included in timing reports.

The observer does not enforce the planned stage budgets in
`protection_stage_time_limits.py`, start security scans, persist or reset
preferences, select Enhanced, clear quarantine, or authorize opening. Even a
complete measurement is **not** evidence that the PDF is clean. A future,
independently reviewed production orchestrator must decide which inspections
to run and enforce time/memory isolation before activating Enhanced.
