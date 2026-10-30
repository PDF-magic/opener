# Scan This PDF eligibility gate (opener-0757, §12.2)

`createScanThisPdfEligibilityGate(coordinator)` provides an inert, opt-in
availability gate for the **Scan This PDF** toolbar control introduced by
opener-0756 (PR #514). It is separate from the existing manual **Scan PDF**
action and does not change its behavior.

An authenticated future integration must supply a coordinator whose own
`currentPdfScanReady` property is exactly `true`, with own callable
`readCurrentPdfEligibility()` and `requestCurrentPdfScan()` methods. The
eligibility method must synchronously return an exact plain object with
five own boolean-`true` fields:

- `pdfIdentified`: an eligible PDF was identified by independently trusted evidence
- `currentDocumentVerified`: the selection is the user's current document
- `selectionVerified`: source identity is authenticated and bound to that document
- `sourceAccessible`: the coordinator can access the intended local/source PDF safely
- `permissionGranted`: all applicable browser access and user permissions are present

All other records, missing evidence, accessors, inherited flags, exceptions,
promises, network URL hints, and ordinary passive PDF candidate objects fail
closed. Candidate metadata is **not** authorization to scan or open.

`gate.state()` rechecks the live coordinator each time. `gate.updateControl(button)`
also rechecks and updates `disabled` and `aria-disabled` together, but only
for a separately supplied extension-owned `button#scanThisPDF`. Future
integration must invoke this on current-document changes, permissions
revocation, scanner disconnect and popup opening, and independently recheck
the selection and capabilities immediately before any eventual scan request.
Simply displaying an enabled control is not proof of a safe document.

**Important prerequisite:** The current browser extension is deliberately
inactive, with no authenticated current-document selector or browser-to-native
scanner bridge. Its `popup.html` remains permanently disabled in the shipped
build. This module does not install popup scripts or listeners, grant browser
permissions, submit scans, read page content, or confer an opening verdict.
Actual live activation is blocked until that separately reviewed integration
is available; the toolbar presentation PR #514 also must land. The native
ClamAV, signature freshness, quarantine, file integrity, and user-selected
PDF application rules are untouched.

`tests/scan-this-pdf-eligibility.test.mjs` verifies the affirmative gate,
revocation, malformed/hostile evidence, exact button targeting, and absence
of scanning side effects. It is discovered automatically by the existing
required WebExtensions `npm test` CI step.
