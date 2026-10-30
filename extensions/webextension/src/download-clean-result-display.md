# Display verified clean download scan results (opener-0695)

`displayVerifiedCleanDownloadScanResult(target, nativeReply,
{ requestId, scanRequestId })` is a **presentation-only** renderer for an
injected, trusted extension UI status element. It returns `true` only when
it renders a verified clean result, otherwise `false` and a neutral
**"No verified clean scan result is available."** message. The status
element uses `role="status"` and `aria-live="polite"` for accessibility.

The renderer accepts a strictly shaped native `scan.result` version-1
response envelope, matching **both** the envelope's `requestId` and the
locally owned `scanRequestId`, and a completed result with:

- `payload.status === "complete"`
- `payload.scanCompleted === true`
- `payload.scanVerified === true`
- `payload.authorizesOpen === false`
- exactly `payload.result = { status: "clean" }`.

The result status `clean` follows the existing native canonical
`ScanResultStatus.clean`. Every nonclean or ambiguous result is refused,
including `malwareDetected`, `scanFailed`, `incompleteScan`,
`scanTimedOut`, `fileChanged`, `cancelled`, and incomplete or
unavailable replies. Extra fields, forged request IDs, inherited values,
property accessors and malformed status claims fail closed. Each refused
response **clears a previously rendered success** so it cannot leave a
stale clean indicator. The renderer uses only constant `textContent`
strings: no filenames, file paths, URLs, native diagnostics, arbitrary
HTML or user-controlled scanner output are shown.

**Security boundary:** Only a **separately authenticated, trusted native
scan coordinator** may supply the response to a trusted extension UI.
Boolean `scanVerified` and `status` fields inside caller-provided JSON
are not themselves authentication or proof of a clean scan. The coordinator
must independently verify scanner evidence, correlate the request to the
specific download, retain mandatory ClamAV freshness, full-file scanning,
unchanged-file integrity, quarantine and final open-authorization checks.
A clean scan result is **not** itself an instruction or permission to open
a PDF. Download-created/completed events, browser danger flags,
`submitCompletedPdfDownloadToNative` acknowledgments, and the scan-once
gate's `request-submitted` outcome are never clean results.

The current standalone native messaging host is deliberately
**transport-only**. Its `scan.result` reply is
`{ status: "unavailable", result: null, scanCompleted: false,
scanVerified: false, authorizesOpen: false }`. Consequently the installed
extension has no verified clean results to display yet. This task adds
the scoped, testable rendering capability but does **not** activate
the shipped inactive browser background or popup, create a fake clean
result, request additional permissions, install a scanner, or modify
any user-defined preferences. Wiring the future authenticated coordinator
to a trusted visible UI is a separate prerequisite to showing production
results. The static popup's disabled Scan PDF control and informational
"Not active" status are intentionally preserved.

`tests/download-clean-result-display.test.mjs` runs automatically with
the existing WebExtensions `npm test` suite under GitHub Actions
`scanner-tests`. It covers correlated clean results, the real
transport-only unavailable reply, every canonical nonclean outcome,
submission-only acknowledgments, malformed data, stale-success removal,
privacy, safe text rendering, accessibility and no startup side effects.
