# Passive PDF `<object>` identification (opener-0743)

`detectPdfObjectEmbed({ tagName: "object", data, type? })` identifies PDF
**candidates** represented by normalized attributes of an HTML `<object>`
element. It accepts an explicit `application/pdf` / `application/x-pdf` type
for a supported, nonempty `data` URL (including extensionless references), or
an untyped `data` path ending in `.pdf` (case-insensitive, with optional query
or fragment). Relative object paths resolve against a fixed, non-page base for
classification only; no page URL is needed. A declared non-PDF type always
vetoes a misleading `.pdf` suffix.

The helper deliberately does **not** parse HTML, walk the DOM, read object
content, fetch resources, inspect bytes, register a content script, or request
browser/host permissions. An authorized future integration must separately
extract only the `tagName`, `data`, and `type` attributes, validate the source
and obtain any necessary user/site consent. The existing extension has no
website permissions and remains inactive; it cannot yet automatically find
objects on live pages. This task adds only the pure classification step.

Unsupported URL schemes (`data:`, `blob:`, `javascript:`, etc.), malformed or
oversized attributes, explicit non-PDF types, non-object elements, unknown
fields, getters and proxy errors return no candidate. A PDF match returns only
immutable `{ isPdfCandidate: true, evidence: "object-type" | "object-data",
authorizesOpen: false }` without the URL, filename or HTML content. A declared
`type` is page-controlled metadata, **not** proof of valid or malware-free PDF
bytes; no classification can authorize scanning, bypass the ClamAV signature
and file-integrity gates, or change the user's destination-app preferences.

The dependency-free Node test suite includes `tests/pdf-object-embed.test.mjs`.
The required `scanner-tests` job already runs `npm test`, whose existing
`tests/*.test.mjs` discovery executes these regression tests without adding
another overlapping CI workflow edit. No new runtime permissions or scanner
integration are introduced.
