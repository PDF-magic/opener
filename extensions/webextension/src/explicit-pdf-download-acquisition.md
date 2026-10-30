# Explicit PDF acquisition through supported browser downloads (opener-0764)

The dormant `createExplicitPdfDownloadAcquisition` adapter uses the
WebExtensions `downloads.download({ url, saveAs: true,
conflictAction: "uniquify" })` API for an explicitly selected PDF **only
when invoked** by a separately authenticated, consented browser integration.
This is a supported browser acquisition mechanism, not a raw network fetch.
The API requires the extension's already-declared optional `downloads`
permission, and the helper checks its effective grant with
`permissions.contains`; it never asks for new permissions itself.

The caller supplies an exact `describeExplicitPdfScanRequest`-compatible
intent record and a trusted coordinator. The coordinator must independently
verify the direct user gesture, source identity and current tab/frame,
preserve the PDF's selected revision, check the local-copy reuse-first
decision, and guarantee that the browser's download/auto-open settings
cannot bypass native scanning. Its `sourceAcquisitionReady`,
`sourceAcquisitionNeeded`, `browserDownloadSafetyReady` and
`nativeScannerReady` flags are **integration gates only, not attestations
or cryptographic proof**. The coordinator's own `resolveVerifiedPdfSource`
returns the bounded HTTP(S) URL for the exact current `selectionId`;
neither a webpage URL nor the scan-request metadata can supply it.
`readCurrentSelectionId` is checked across asynchronous steps.

No browser permission, native scanner or trusted current-document adapter
is wired into the shipped extension. The background worker remains inert.
If any of the prerequisite gates is missing, nothing is downloaded.

Successful initiation returns only an immutable numeric browser download
ID and `status: "download-started"`, with `scanVerified: false`,
`authorizesScan: false` and `authorizesOpen: false`. This does NOT
mean transfer completion, PDF content authenticity, native file access or
malware clearance. The existing download-completion and native scan
preflight mechanisms must independently verify the final download
(particularly after redirects), browser warnings and the stable local
file before any native scan, and the native policy must still enforce
current ClamAV signatures, integrity, quarantine and selected-app opening.
The helper never opens a PDF or changes saved browser preferences.

The adapter rejects malformed URLs, reused IDs, absent grants, stale
selection, revocations and unsafe source metadata. A permission loss or
navigation after a download begins requests best-effort
`downloads.cancel(id)`; browser APIs cannot promise cancellation before
completion, so **a future integration must separately establish fail-closed
download auto-opening policy** before enabling this path.
A reuse-first coordinator should use opener-0761/0762 existing-copy
checks to avoid initiating redundant transfers.

The Node regression suite covers accepted calls, permission denial,
invalid sources, races, revocation, cancellation, one-shot semantics,
immutable privacy-safe results and unchanged inactive extension privileges.
It is run both by `npm test` and as a dedicated `scanner-tests`
GitHub Actions step.
