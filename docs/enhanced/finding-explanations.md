# Explainable Enhanced PDF finding results (opener-0299)

`enhanced_finding_explanations.explain_analysis_findings(report)` decorates
the immutable structured stage findings from [opener-0297](../structured-enhanced-findings.md)
with a **result for every finding**. Each finding retains its fixed code,
stable `findingId`, severity and optional bounded object/page location, and
receives a nested `result` object with:

- `outcome`: `recorded`, `reviewRequired`, `blocking`, or `inspectionIncomplete`
- `explanation`: a fixed, human-readable reason tied to the finding code
- `nextAction`: fixed safe handling guidance, never execution of PDF content
- `malwareAssessment`: always `notConfirmed` for Enhanced analysis findings

Normal informational observations are recorded but are not a clean verdict.
Review-required and suspicious observations both require human review before any
opening decision. Explicit `blocking` and `critical` observations stop opening;
resource-limit and inspection-failure findings **always** report
`inspectionIncomplete` and require blocking, even if a producer marks their
severity informational. The explanation never claims that JavaScript
executed, a URL was contacted, or an embedded binary ran.

The adapter serializes a **schemaVersion 2** copy of the parent v1 report,
preserving every finding, ordering, stage outcome, object/page reference, and
explicit `notRun` record. It does not alter the original report. A missing
or incomplete expected stage remains blocking. Results use only an exhaustive
table of fixed, code-specific text and action identifiers. No document-supplied
filenames, URLs, scripts, paths, attachment bytes or error text are interpolated.

The fixed `knownMaliciousContent` code is a code-level blocking response even
when the producer reports informational severity. It always returns `blocking`
and `stopOpening`; the native progress display independently validates this
minimum response and rejects downgraded or inconsistent results.

Example (once the structured findings contract is available):

```python
from enhanced_analysis_findings import (
    AnalysisFinding, AnalysisStage, FindingCode, FindingSeverity,
    StageAnalysis, StageOutcome, StructuredAnalysisFindings,
)
from enhanced_finding_explanations import explain_analysis_findings

source = StructuredAnalysisFindings(
    (AnalysisStage.embeddedUrls,),
    (StageAnalysis(
        AnalysisStage.embeddedUrls, StageOutcome.completed,
        (AnalysisFinding(FindingCode.suspiciousUrl, FindingSeverity.suspicious),),
    ),),
)
payload = explain_analysis_findings(source).to_dict()
assert payload["stageResults"][0]["findings"][0]["result"]["outcome"] == "reviewRequired"
assert payload["authorizesOpen"] is False
```

This passive reporting adapter does not parse PDFs, inspect new features,
activate Enhanced, authorize opening, grant a clean verdict, change the installed
ClamAV gate, alter quarantine or caches, or modify user settings. It depends on
the reporting contract in [PR #190](https://github.com/PDF-magic/opener/pull/190),
so the PR may be stacked temporarily until that contract lands. Producer
integration and safety-policy activation are separate checklist tasks.

## Heuristic evidence is not a confirmed malware detection

Every Enhanced finding carries `result.malwareAssessment = "notConfirmed"`,
regardless of its severity or handling outcome. A `blocking` result means the
policy stops opening; it does **not** mean malware was confirmed. Heuristic
signals such as suspicious URLs, active-content capabilities, and unexpected
embedded files can justify review or blocking without proving that a payload
executed or that the document is malware.

The native scan-progress panel labels these findings **“Malware not confirmed”**
and rejects any unknown malware-assessment value. Older schema-v2 reports that
lack this additive field are treated as unconfirmed, never as confirmed malware.
The separate ClamAV scan-result contract uses `malwareDetected` for a scanner
reported detection; its wording is not reused for heuristic findings. None of
these reporting fields authorizes opening or changes the deployed scan gate.


## Optional technical details in the native progress panel (opener-0482)

The native scan-progress panel keeps its ordinary progress layout compact when a
validated Enhanced findings report is available. The findings summary and a
**Show technical details** disclosure remain visible; the detailed selectable
report is collapsed until the user asks to view it. The control changes to
**Hide technical details** while expanded and restores the compact layout when
collapsed. An unavailable or invalid report still shows a safe summary and a
fixed explanation only when requested—never PDF-controlled text or paths.

This is presentation-only. The disclosure does not change finding severity,
policy, scan state, cancellation, quarantine, the ClamAV gate, or whether a PDF
may open. A summary with no reported findings is not a clean verdict.
