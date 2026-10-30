# Embedded PDF context-menu action contract (opener-0759)

`src/embedded-pdf-context-menu.js` introduces an explicit
**Scan This Embedded PDF** context-action model. A future, independently
permissioned browser adapter can use `embeddedPdfContextMenuState(snapshot)`
to decide whether a *trusted* element snapshot represents a supported PDF.

Only existing, reviewed passive classifiers are used:
- `detectPdfIframe` for an `iframe` with a supported PDF URL path in a
  non-top frame;
- `detectPdfEmbedElement` for an `embed` with supported PDF URL-path or
  PDF type evidence in a valid tab/frame.

Object-element support is separately under review in opener-0743 and is
not included. Arbitrary links, non-PDF page resources, unsupported URLs,
missing/hostile metadata and untrusted input fail closed.

The returned menu descriptor has a stable ID and title but is **disabled**.
The action always returns `not-requested`, `unsupported` or `unavailable`,
with `authorizesScan: false`, `scanVerified: false` and
`authorizesOpen: false`. No URLs, paths or page content escape through
results. This intentionally does **not** register a visible browser
`contextMenus` entry: the current Manifest V3 scaffold grants no
`contextMenus` permission and the background worker is deliberately inert.
Presenting an actionable menu before a verified native scanner and
authenticated element provenance exist would mislead users and risk bypassing
the mandatory scan-before-open gate.

**Prerequisite for an operational context menu:** a separately reviewed
browser adapter with the appropriate context-menu permission and event
registration, authenticated association between the clicked element and PDF
content, consent to any necessary site/file access, and a trusted native
scan coordinator. The installed ClamAV, signature freshness, integrity,
quarantine and verified scan-before-open requirements remain mandatory.
No browser permission, native connection, user preference or scanner behavior
changes in this focused implementation.

`tests/embedded-pdf-context-menu.test.mjs` is included automatically by
the shared WebExtensions `npm test` job and GitHub `scanner-tests` CI.
