# Display scanner-unavailable download errors (opener-0700)

`createDownloadScannerUnavailableDisplay(root)` is a passive,
extension-owned presentation adapter for a failed scanner-availability
check during a PDF download scan. It never connects, scans, opens a
document, requests permissions, registers background listeners or changes
the installed scanner, signature policy, quarantine, or user preferences.

The calling integration must use an extension-owned DOM element and
independently authenticate the native host or establish the missing
scanner from trusted **local connection lifecycle** observations.
No raw browser error, filename, host path, scanner stderr or attacker
supplied message is placed in the DOM.

A trusted integration can call `showLocalUnavailable()` when it
determines no verified native scanner is available, or call
`show(message, { requestId, scanRequestId })` with an independently
verified, matching, version-1 response from the existing protocol:

- `scan.request`: an unavailable response with
  `trusted-scan-coordinator-required` and every scan/open flag false
- `scan.status`: the same unavailable response correlated to its exact
  `scanRequestId`
- `scan.result`: an unavailable, incomplete result (`result: null`)
  with the same trusted-coordinator prerequisite and all authority
  flags false
- `host.connection`: an explicitly recognized, local, sanitized
  native connection error code; it is **not** a reply from a disconnected
  host or proof of scanner execution

Other statuses, missing or conflicting identifiers, progress,
unexpected fields, claimed clean/malware verdicts, override values,
foreign properties, getters and hostile proxy objects are refused.
An unrelated response clears any prior availability warning rather than
leaving a stale error on screen.

The component uses only fixed `textContent` nodes in an
`aria-live="assertive"`, `role="alert"` display:

> Scanner unavailable — PDF not scanned
>
> The required native scanner is unavailable. This PDF was not
> verified and must not be opened through PDF Magic Opener.

The returned `{ status: "displayed", scannerUnavailable: true,
scanVerified: false, authorizesOpen: false }` is immutable and carries
no file metadata. `clear()` removes the message;
`dispose()` disables the display; neither changes scanner state.
Showing an error never establishes malware, a successful scan,
scan completion or PDF-opening permission.

The packaged extension remains intentionally inactive. Its existing
disabled Scan PDF button continues to describe the missing native
scanner. A future reviewed, authenticated download-scan UI may invoke
this module to display actual scanner-unavailable events; until that
integration exists this file does **not** activate background scanning
or claim that an unavailable scan has been attempted.

Run `node --test tests/download-scanner-unavailable-display.test.mjs`
from `extensions/webextension`. The existing required
`scanner-tests` CI executes all `tests/*.test.mjs`.
