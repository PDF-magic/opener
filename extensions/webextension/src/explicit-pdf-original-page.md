# Preserve access to the original page during Scan This PDF (opener-0775)

The browser Scan This PDF flow should not replace or close the original
website tab just because the user selected a PDF link or embedded PDF. A
browser download can run separately while the user retains the page, login
context, form state and ability to select another document. The existing
explicit browser acquisition adapter starts `downloads.download()` with
`saveAs:true` and `conflictAction:"uniquify"`; it does not call `tabs.update`
or `tabs.remove`.

`createExplicitPdfOriginalPagePreservation(coordinator)` adds a **passive,
opt-in preservation contract** around a trusted explicit scan request. It
does not register browser navigation listeners, modify tabs, fetch PDFs,
open downloads or connect to a native host.

## Original-page rules

The coordinator must independently authenticate the user gesture, browser
tab/frame, current selection, original **top-level** page identity, and the
browser's current access grants. It provides:

- `originalPagePreservationReady: true`, an explicit trusted capability.
- `readVerifiedOriginalPage(reference)`, a synchronous, network-free,
  browser-attested snapshot of exactly `requestId`, `tabId`, `frameId`,
  `selectionId`, `pageId`, `documentRevision`, `pageKind`,
  `verified:true`, and `permissionGranted:true`. `pageId` is an
  opaque top-level document identifier, **never a URL or file path**. In an
  embedded iframe, it still identifies the **containing website's** page.
- `requestPdfScanWithoutNavigation(reference)`, returning a Promise that
  resolves to exactly `{accepted:true}` **only after** an authenticated,
  non-navigating explicit scan request is accepted. The callback must not
  navigate, replace, close, discard, redirect, or steal focus from the
  originating tab. It must use the existing verified download/native
  scanner flow, with no URL replay or implicit file opening.

For a PDF link or embedded PDF, the original page must be a verified
`html-page`. The toolbar can also be invoked in a standalone `pdf-viewer`
tab; in that case the preservation-of-original-HTML-page rule does not
apply. No case automatically navigates to another page.

Before invoking the coordinator, the guard requires a validated versioned
seven-field explicit scan request and a verified current page. The request
ID is reserved once, before the asynchronous callback, so a double click,
retry or denial cannot start a second operation. The guard initiates the
coordinator in the same action-handler call stack before its first await.
After the callback resolves, it rechecks the **same page ID, revision,
tab/frame/selection, page kind, access grant and coordinator methods**.
A reload, navigation, tab replacement, revoked access, stale selection,
invalid response or disposed guard fails closed. Results contain no URL,
form state, credentials or private paths, and no scan/open authorization.

`status:"request-submitted"` with `originalPagePreserved:true` means only
that a trusted coordinator attested the same HTML document immediately
after accepting the non-navigating request. It **does not prove ongoing
browser-tab availability**, file acquisition, completed scanning or safety.
For `pdf-viewer` requests, `originalPageApplicable:false` and
`originalPagePreserved:false` deliberately avoid implying an HTML source
page exists. Even a successful request cannot bypass ClamAV signature
freshness, file identity, quarantine, download warnings or the user's PDF
application choice.

## Production integration prerequisite

The installed WebExtension is deliberately inactive, with no new tab,
navigation, host or native permissions. A future browser coordinator must
implement and enforce the no-navigation rule; the guard can detect a
changed page at the final check but cannot undo navigation performed by
a misbehaving host, keep tabs alive across browser closure, or restore a
previous URL. **Never automatically reopen the original page**, because
its URL might contain bearer tokens and restoring it could discard user
changes, repeat an authenticated request or cause unsafe navigation.

The same integration must remain compatible with the existing download
timeout, size, signed URL, consent, access controls and native mandatory
scan-before-open contracts. Nothing in this task alters those protections or
user customization.

`tests/explicit-pdf-original-page.test.mjs` contains 15 Node regression
groups for HTML page preservation, embedded-frame identity, standalone
PDF viewers, tab replacement/reload, duplicate clicks, expired permissions,
malicious inputs, callback failure and cleanup. The existing WebExtensions
`npm test` wildcard includes this suite in the `scanner-tests` GitHub CI.
