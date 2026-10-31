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

## Document name and selected protection level

The same `show(_:documentURL:selectedProtectionLevel:)` call accepts the
trusted local document URL and selected protection level from the scan-request
owner. Only the **basename** appears in the summary and accessibility label;
directory paths, remote URLs, control characters, bidi overrides and oversized
names display `Document: Unavailable`. Input is presentation data, never a
scanner operand or file-opening authorization.

The selected level is a typed `ScanResultSummaryProtectionLevel`. The only
deployed and enforced scanner is **Built-in**. Standard, Enhanced and Maximum
are inactive preference previews and are explicitly marked `preview only;
Built-in scanning remains active` if displayed. Missing or unsupported
selections show `Selected protection level: Unavailable` rather than
silently treating an unknown selection as Built-in. The component does not
read or modify saved settings.

Each new result update clears missing contextual fields, and `reset()`
clears the document name, selected level and prior verdict together. The
existing portable and macOS rendering suites verify Unicode, privacy,
inactive-preview explanations, accessible labels and fail-closed reset behavior.

## Whether sanitization was performed

The same trusted `show(_:documentURL:selectedProtectionLevel:sanitization:)`
call accepts an optional typed `ScanResultSummarySanitization` value.
`performed` renders **Sanitization: Performed** only after the trusted
coordinator establishes that conversion completed with verified generated
output. `notPerformed` renders **Sanitization: Not performed** only when it
explicitly knows no conversion occurred.

Missing evidence, a pending attempt, and failed or unverified conversions
display **Sanitization: Unavailable**. Never infer completion from a clean
scan, selected Maximum preview, attempted conversion, or document content.
The accessible label uses the same fixed text. Every `show` update and
`reset()` clears prior evidence unless freshly supplied for the current
request. Conversion does not authorize opening or replace scanning and
file-integrity checks. The existing required portable and macOS rendering
suites now check these states; scanning and preferences remain unchanged.

## Malware detection display

The summary always includes an accessible, explicitly labelled malware status.
A trusted `.malwareDetected` terminal result displays **Malware: Detected**;
only a trusted `.clean` result displays **Malware: Not detected**. Every
other terminal outcome and `nil` displays **Malware: Not determined**, never
mistaking a scanner failure, cancellation or incomplete inspection for a
negative malware finding. Each new `show` call and `reset()` replaces the
previous text; a former clean result cannot be carried into another request.

The label is presentation-only and receives the same trusted canonical status
as the existing heading. It does not infer status from file content, scanner
logs, document names or user preferences, and it does not grant permission
to open a PDF. Portable contract tests and the macOS AppKit rendering harness
cover every canonical outcome, accessibility, isolation and reset in required CI.
