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

## Verified opening and blocking outcome (opener-0879)

The reusable AppKit summary shows three accessible fields: **File opened**,
**File blocked**, and a short **Blocking reason**. A clean scan is **not** proof
that the file opened: until the trusted scan-request coordinator confirms the
post-scan opening handoff, both fields say `Not confirmed`. Only the typed
`openingOutcome: .opened` accompanying a trusted `.clean` terminal scan
result can display `File opened: Yes`. An explicit `.blocked` post-scan
outcome displays `File blocked: Yes` with a fixed opening-failure reason.

Every non-clean terminal scan status displays `File opened: No` and
`File blocked: Yes`, with a short, status-specific reason (malware,
structure, encryption, incomplete scan, scanner failure/timeout, changed or
oversized file, or cancellation). A contradictory `.opened` outcome cannot
override a non-clean status. An absent trusted status remains `Not confirmed`
regardless of the supplied opening outcome. New `show(...)` calls and
`reset()` clear previously displayed handoff results.

The copy is fixed and never prints an input file path, parser message, scanner
stderr, or caller-controlled block reason. The component does not itself open
or block a file, nor does it claim to observe the app's window; the trusted
caller must supply an actual completed handoff result. This presentation-only
change does not wire a new result window into the installed scan workflow or
change scanner enforcement, saved settings, or user customizations. Existing
required Linux contract tests and macOS AppKit rendering tests cover the new
outcomes.
