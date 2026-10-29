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
expected stage or suspicious/critical finding. When every *reported* stage
completes with no blocking findings, this signal may be false, but it is **not**
a clean verdict and never authorizes opening. The caller's trusted requirements
must include all applicable inspection stages; remaining baseline checks and the
existing verified scanner/handoff protections are independent and mandatory.

This contract can be integrated with [the maintained PDF parser PR #179](https://github.com/PDF-magic/opener/pull/179)
and the individual Enhanced inspection stages once they are reviewed and merged.
Until then, Enhanced remains unavailable and the installed Built-in scan gate
continues unchanged.
