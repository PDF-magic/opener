# Reuse an existing local PDF for explicit scanning (opener-0762, §12.2)

The \`planExplicitPdfLocalReuse({ coordinator, selectionId })\` helper applies a
**reuse-first source policy** for an explicit **Scan This PDF** action. If an
independently authenticated trusted coordinator reports that the *selected*
current PDF already has a verified, stable, complete local copy, the plan is
\`reuse-existing-local\`. No second download is needed. If the coordinator
affirmatively reports that the selected PDF is **not present locally**, the
plan is \`source-acquisition-needed\` so a separate reviewed integration can
decide whether and how to obtain it. Missing, partial, unverified, ambiguous
or changed files do **not** cause automatic reacquisition; they return
\`unavailable\` and must be dealt with by the trusted integration.

The injected coordinator must have an own
\`localPdfReuseReady: true\` property and own callable
\`readCurrentPdfSelection()\` and \`inspectExistingLocalPdf(identity)\` methods.
The first method returns exactly seven own data fields:
\`selectionId\` (bounded opaque ID), \`documentRevision\` (nonnegative safe
integer), and exactly-true \`pdfIdentified\`,
\`currentDocumentVerified\`, \`selectionVerified\`, \`permissionGranted\`,
\`userInitiated\`. This data must come from trusted current-document context,
not from page scripts, filenames or URL hints.

The asynchronous inspection receives a frozen
\`{ selectionId, documentRevision }\`, **never a URL or path**.
It must independently establish file identity, file stability, completed
transfer and matching current PDF. It returns exactly either:

- \`{ selectionId, documentRevision, status: "verified-local",
  identityVerified: true, transferComplete: true, fileStable: true }\`
- \`{ selectionId, documentRevision, status: "not-present" }\`

The helper rejects extra fields, inherited/accessor properties and mismatched
identity or revision, and rechecks the current document and permission after
the awaited inspection. A native integration must additionally prevent a
selection from becoming invalid during an actual scan. An inspection result
is not a malware verdict, and the coordinator must revalidate the real local
file immediately before native scan dispatch.

**No automatic network activity is introduced.** The helper never invokes
a downloader, requests browser permissions, reads bytes or paths, registers
listeners, submits scans or opens PDFs. Results contain only frozen status and
booleans: \`authorizesDownload\`, \`authorizesScan\`, \`authorizesOpen\`,
\`scanVerified\` and \`downloadStarted\` are always false. A plan that needs
acquisition does *not* grant consent to download. The browser extension
remains inactive and its **Scan This PDF** toolbar control remains disabled
until the separately reviewed authenticated browser-to-native selection and
scan-request integration is available. Do not confuse local reuse with a
cached-clean ClamAV verdict: the existing signature freshness, file identity,
quarantine, scan-before-open and user-selected PDF app policy remain mandatory.

\`tests/explicit-pdf-local-reuse.test.mjs\` covers reuse vs missing source,
document-revision changes, incomplete and malicious metadata, permissions,
consent, privacy, and the absence of network/scanner effects. The existing
WebExtensions \`npm test\` wildcard runs these tests in required CI.
