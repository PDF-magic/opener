# Passive HTML iframe PDF identification (opener-0745)

`detectPdfIframe(record)` in `src/pdf-iframe.js` identifies PDF candidates
embedded through an HTML `<iframe src="...">` reference. It accepts an explicitly
provided, normalized record such as:

```js
detectPdfIframe({
  tagName: "IFRAME",
  src: "../report.pdf",
  documentUrl: "https://example.invalid/account/index.html"
});
// { isPdfCandidate: true, evidence: "iframe-src", authorizesOpen: false }
```

The classifier resolves relative, absolute and protocol-relative HTTP(S) URLs
against an optionally supplied trusted containing-document URL and delegates
PDF suffix identification to the shared `detectPdfCandidate` URL-path parser.
It ignores query/fragment-only PDF names and rejects malformed URL escapes,
unsupported schemes, other tag types, `srcdoc` frames, inherited/accessor
properties and unrecognized page content. A page-authored `type` claim is not
PDF evidence; a .pdf-looking URL is **not** proof of the response MIME type,
PDF bytes or safety.

This is a **passive candidate classifier**, not a live DOM observer. The shared
WebExtension intentionally has no content scripts, host permissions or active
background listeners. A later separately authorized browser adapter would have
to supply only normalized iframe attribute metadata to use this classifier
on an actual page; it must not hand over page HTML, scrape frames, or treat
untrusted page-provided metadata as authority to open files. The result never
contains a URL, path, document content or opening authorization.

Existing user-selected application settings, mandatory native ClamAV scanning,
signature freshness, integrity, quarantine and scan-before-open protections
remain unchanged. No permission is requested, network content fetched,
download initiated, file scanned or PDF opened by this helper.

`npm test` auto-discovers `tests/pdf-iframe.test.mjs` within the
WebExtension test suite already run by the repository's required CI workflow.
