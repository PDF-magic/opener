# Exclude unrelated page resources from PDF identification (opener-0752)

`classifyPdfDocumentResource(details)` is a passive, browser-neutral scope
gate for future independently authorized browser response/navigation adapters.
Only real document-navigation resource types qualify: `main_frame` with
`frameId: 0`, and `sub_frame` with a positive frame ID, in a valid tab.
Scripts, stylesheets, images, fonts, media, XHR/fetch, websocket, plugin and
other ordinary page resources are **not** PDF candidates, even when their URLs
end in `.pdf` or response metadata claims a PDF MIME type. No page resource
enumeration or scanning occurs.

Top-frame documents use the existing strict `detectPdfResponseMime` validator
when response MIME metadata is available. Invalid or non-PDF declarations
cannot be overridden by a misleading `.pdf` URL suffix. When MIME metadata
is absent, the existing `detectPdfNavigation` classifier supplies path-only
candidate evidence. Subframe document candidates use PDF URL-path evidence;
their response MIME is not interpreted by a main-frame-only validator.
Embedded object/iframe, privileged viewer and supported blob workflows remain
separate tasks, not an invitation to inspect every resource on a page.

The return value is frozen and path-free and contains only
`{ isPdfCandidate, evidence, authorizesScan: false, authorizesOpen: false }`.
**A PDF candidate is not verified content and never authorizes scanning or
opening.** Future integration must authenticate the browser event, verify
actual PDF bytes and enforce the existing ClamAV/signature freshness,
quarantine, integrity and native scan-before-open protections. User-selected
applications and stored preferences remain unchanged.

No browser listeners, permissions, DOM/content access, network calls, native
messages, scanner commands or user customizations change. The background
remains inert. `tests/pdf-resource-scope.test.mjs` is automatically run by
`npm test` in the required GitHub `scanner-tests` CI job.
