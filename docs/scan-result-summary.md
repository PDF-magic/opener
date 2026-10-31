# Reusable native scan result summary

`scan-result-summary-view.swift` provides an AppKit `ScanResultSummaryView`
that can be embedded in a native result panel, notification detail, or other
trusted presentation surface. It is independent of the scanning progress panel.

The owner creates a view and calls `show(_ status: ScanResultSummaryStatus?)`
with a **trusted canonical terminal status**. The ten typed cases mirror
`scan_results.ScanResultStatus`; `nil` (including the initial state) displays
a neutral “No verified scan result” notice. Call `reset()` when changing
requests so a former clean result never remains visible. Instances retain their
own UI state and use system font sizing and accessible labels.

All headings and explanations are fixed, path-free, and separate scanner errors
from confirmed malware. Even the clean summary says further file-integrity and
verified-opening checks apply. The view never evaluates a scanner response,
verifies a document, starts a process, changes preferences, removes quarantine,
releases a file, or grants authorization to open.

**Trust boundary:** Caller code must independently establish the result status
from the authoritative native scan gate and correlate it with the correct
document. Never map page text, extension messages, arbitrary JSON, or raw
subprocess output directly into a displayed clean result. The current change
introduces the reusable component only; it does not activate a new result window
or alter the installed Built-in scanning flow.

`tests/scan/result-summary-component.py` checks canonical status parity and
read-only constraints; `test-scan-result-summary.swift` verifies rendering,
accessibility, independent instances and reset behavior on macOS. Both are
included in required CI.
