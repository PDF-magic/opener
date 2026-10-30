# Passive browser PDF navigation detection (opener-0737)

`detectPdfNavigation(details)` in `src/pdf-navigation.js` identifies a
**candidate top-level navigation** to a URL whose final path component ends in
`.pdf` (case-insensitively). It reuses the existing, reviewed
`detectPdfCandidate({ url })` URL-path parser. Percent-encoded path characters,
trailing query strings and fragments are handled by that existing parser;
`.pdf.exe`, trailing path components, a `.pdf` only in query/fragment text,
non-web/unsupported URL schemes and malformed encodings do not match.

Call it **only** with metadata supplied by an independently trusted browser
navigation API (such as `webNavigation.onCommitted`), rather than webpage
scripts, extension messages, arbitrary strings or browser-download filenames.
The event must contain a nonnegative safe-integer `tabId`, `frameId: 0` and a
string `url`. Subframe navigations and missing or malformed fields are not
classified as top-level PDF navigations. No event metadata or URL is returned:
the frozen result is `{ isPdfCandidate, evidence, authorizesOpen: false }`.
The detector is **only a candidate classifier**, not a content validation,
network response verification, malware verdict or opening authorization.

## Prerequisite for live navigation observation

The browser extension background module is deliberately inactive, and the
shared Manifest V3 declares no `webNavigation` permission or host permissions.
**No live browser navigation events are subscribed to by this task.** A later
reviewed, user-authorized and browser-compatible listener/permission integration
must supply real browser events; a webpage-provided record is not proof of a
navigation. This task does not request permissions, modify manifests, intercept
or cancel browsing, connect to native messaging, scan downloads or launch PDFs.
The Safari and other browser packages remain in their original inert state.

Even if a filename or URL ends in `.pdf`, it may be mislabeled or malicious.
The installed PDF Magic Opener's existing native ClamAV/signature freshness,
integrity, quarantine and verified scan-before-open requirements continue to
govern any supported file opening. User-selected applications and browser
preferences remain unchanged.

The shared WebExtensions `npm test` automatically discovers
`tests/pdf-navigation.test.mjs`. Required GitHub CI also runs that focused
suite explicitly to verify recognition, malicious-input rejection, top-frame
validation, immutable privacy-safe results and the unchanged inactive extension.
