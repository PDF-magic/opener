# File-size failure display for downloaded PDFs (opener-0699)

`createDownloadFileSizeFailureDisplay(root, coordinator)` is a passive,
extension-owned DOM renderer for a **verified native** `fileTooLarge`
scan outcome. It follows the existing download malware-detection display's
trusted-report boundary, without duplicating native scanning or registering
any browser listeners. It does **not** enable the currently inert extension
background or connect to the current transport-only native host.

## Input and verified result

A separately authenticated native scanner coordinator must provide the own
data properties `nativeScanResultsReady: true` and an asynchronous
`readVerifiedDownloadScanReport(scanRequestId)` method. The readiness flag
is **not** evidence of authentication; the native integration must establish
that independently, verify full scan identity and policy, and correlate the
request to its canonical `CombinedScanReport.to_dict()` result.

The module accepts only a bounded request ID and a correlated,
exact-shape `{ scanRequestId, report }` wrapper. The canonical report must
have `schemaVersion: 1`, `authorizesOpen: false`,
`requiresBlock: true`, `scan.status: "fileTooLarge"`, the installed
`clamav.effectivePolicyId: "built-in"`, and **no malware detection names**.
Other outcome statuses (including clean, malwareDetected, incompleteScan,
scanFailed, scanTimedOut and cancelled), malformed/native errors, hostile
getters, extra report fields, or the wrong scan-request ID never show a
file-size warning. A result with malware evidence must not be downgraded
to a size-only message.

## Presentation and security

The extension-owned element becomes visible with `role="alert"` and the
fixed message:

**File too large — scanning blocked**

"The required scanner could not fully inspect this PDF because a file-size
limit was exceeded. The PDF was not opened."

The report schema does **not** provide a trusted exact file size or size
threshold, so the UI must not invent one or recommend bypassing scanner
limits. The implementation creates textContent-only DOM nodes; no raw
native diagnostics, file paths, download URLs, PDF content, or scan request
IDs enter the visible text. `show()` yields a frozen
`{ status: "displayed", fileSizeFailure: true, authorizesOpen: false }`
only when the canonical verified status is present; otherwise the element
remains hidden and the result is an immutable unavailable state.

`clear()` and `dispose()` invalidate late native responses and remove
the alert. A new show call also invalidates old results. The module never
grants file opening, scans PDFs, alters ClamAV limits, adjusts quarantine,
changes the user's PDF application, or requests permissions. Other scanner
failure notifications and user preferences are unchanged.

The current native messaging host is still transport-only; actual live
display requires a **separately reviewed authenticated native scan-result
coordinator** and an extension-owned UI binding. No simulated clean or
size-verdict integration is activated by this task.

The 13 Node regression tests in
`tests/download-file-size-display.test.mjs` are automatically executed by
the existing WebExtensions `npm test` / required `scanner-tests` CI job.
