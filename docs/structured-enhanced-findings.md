# Structured Enhanced PDF analysis findings (opener-0297)

`enhanced_analysis_findings.py` defines a **reporting contract** for future
Enhanced PDF inspection stages. It deliberately does not parse documents,
choose or activate protection profiles, run ClamAV, grant a clean scan verdict,
remove quarantine, or open a PDF.

Trusted callers declare the stages they expect and supply completed or
incomplete `StageAnalysis` records. A missing expected stage is serialized as
`notRun` and is treated as incomplete rather than silently omitted. Findings
contain fixed `FindingCode` and `FindingSeverity` values and optional bounded
PDF object/page numbers, not document-controlled text, URLs, file paths,
attachment names, raw bytes, or exception messages. Data records are immutable;
`to_dict()` creates a separate JSON-serializable object in expected-stage order.

`FindingSeverity` includes `informational`, `reviewRequired`, `suspicious`,
and `critical`. The explicit `reviewRequired` severity records that human
review is mandatory even when the evidence is not separately classified as
suspicious. Both `reviewRequired` and `suspicious` require review before an
opening decision; `critical` blocks. The code-specific blocking policy can
require blocking regardless of severity.

Each finding exposes a deterministic `finding_id` and serializes it as
`findingId`, using the versioned signature
`finding-v1:<code>:object=<number-or-none>:page=<number-or-none>`. The ID is
stable across runs and report ordering, and does not change if policy changes
the finding's severity. It identifies the known finding code and available
location—not a document, a unique event, or a globally unique occurrence.
Identical code/location signatures intentionally share an ID; producers should
include validated locations when the evidence has them. The ID never includes
document-provided text, paths, URLs, stream contents, or random/process-local
values. The additive field preserves schema version 1 and is ignored by older
consumers that only need the existing fields.

Example for a **future** inspection producer:

```python
from enhanced_analysis_findings import (
    AnalysisFinding, AnalysisStage, FindingCode, FindingSeverity,
    StageAnalysis, StageOutcome, StructuredAnalysisFindings,
)

report = StructuredAnalysisFindings(
    expected_stages=(AnalysisStage.embeddedUrls, AnalysisStage.executableContent),
    stages=(
        StageAnalysis(
            AnalysisStage.embeddedUrls,
            StageOutcome.completed,
            (AnalysisFinding(FindingCode.suspiciousUrl, FindingSeverity.suspicious,
                             object_number=12),),
        ),
    ),
)
payload = report.to_dict()
assert payload["requiresBlock"] is True
assert payload["stageResults"][1]["outcome"] == "notRun"
assert payload["authorizesOpen"] is False
```

`requiresBlock` is a conservative **analysis signal** for any unfinished
expected stage or review-required/suspicious/critical finding. When every *reported* stage
completes with no blocking findings, this signal may be false, but it is **not**
a clean verdict and never authorizes opening. The caller's trusted requirements
must include all applicable inspection stages; remaining baseline checks and the
existing verified scanner/handoff protections are independent and mandatory.

This contract can be integrated with [the maintained PDF parser PR #179](https://github.com/PDF-magic/opener/pull/179)
and the individual Enhanced inspection stages once they are reviewed and merged.
Until then, Enhanced remains unavailable and the installed Built-in scan gate
continues unchanged.
