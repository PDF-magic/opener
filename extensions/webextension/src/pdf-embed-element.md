# Identify PDFs in HTML `<embed>` elements (opener-0744)

`detectPdfEmbedElement({ tagName, src, type?, baseUrl? })` is a **passive**
classifier of minimal, already normalized attributes of an actual HTML
`<embed>` element. A future integration must independently authenticate the
element source and obtain any necessary site access and user consent. The
current extension **does not** access DOM elements, collect page HTML, inject
content scripts or request website permissions.

The helper accepts only `tagName: "embed"` (case-insensitive) and a nonempty
HTTP(S) `src`. It identifies PDF candidates from a page-declared
`type="application/pdf"` / `type="application/x-pdf"` or from a standalone
`.pdf` suffix in the final `src` URL path. Relative `src` values require an
explicit HTTP(S) `baseUrl`; the function resolves them without any network
request. Known non-PDF `type` values veto a misleading `.pdf` suffix. Missing
sources, invalid metadata, unsafe schemes (`data:`, `blob:`, `file:`, etc.),
credentialed URLs, ambiguous encodings, oversized input, accessors and other
HTML elements fail closed. This is only a hint: an HTML type declaration can
lie, and a PDF suffix does not prove PDF bytes.

```js
import { detectPdfEmbedElement } from "./pdf-embed-element.js";

const result = detectPdfEmbedElement({
  tagName: "embed", src: "../files/report.pdf",
  baseUrl: "https://example.test/articles/page.html"
});
// { isPdfCandidate: true, evidence: "embed-src", authorizesOpen: false }
```

Only immutable, content-free `{ isPdfCandidate, evidence, authorizesOpen }`
records are returned. This helper never reads page content, fetches an
embedded resource, verifies PDF bytes, scans or opens files, changes
permissions, or selects an application. Any future action still requires
the installed ClamAV scanner, signature freshness, file integrity,
quarantine and user-selected opening preferences; this identifier cannot
bypass them. Browser DOM observation and its separate privacy/permission
review are **not** implemented by this checklist task.

`tests/pdf-embed-element.test.mjs` covers positive and negative `<embed>`
examples, relative resolution, MIME precedence, malformed/hostile metadata,
no data leakage and unchanged extension permissions. `npm test` discovers
this file in the required `scanner-tests` GitHub Actions suite, with an
additional dedicated CI invocation.
