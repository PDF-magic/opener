# Detect attachment navigation responses (opener-0742)

`detectAttachmentResponse(details)` is a passive classifier for a browser's
**observable main-frame HTTP response** metadata. It detects an explicit
`Content-Disposition: attachment` response header, optionally followed by
valid parameters (including quoted filenames and `filename*`). It does **not**
infer attachment status from URL suffixes, filenames, page content or MIME.

The caller must authenticate the browser event and independently verify any
permission needed to receive response headers. The helper accepts only
`type: "main_frame"`, `frameId: 0`, a nonnegative safe-integer tab ID,
and an array of browser-provided `responseHeaders`. Without exposed
headers, the result is not an attachment candidate. Inline dispositions,
duplicate or malformed declarations, control characters, unclosed quotes,
invalid or oversized parameters, hostile getters and unsupported event
contexts fail closed.

An attachment disposition only describes **server-declared presentation**:
it is not proof that the body is PDF data, an indication of cleanliness,
or permission to scan, download, or open. PDF identification remains
independent: see `pdf-response-mime.js` and `pdf-extensionless.js`.
The immutable result contains only
`{ isAttachmentResponse, evidence, authorizesOpen: false }`,
never filenames, URLs, cookies, response headers or other private metadata.

This module adds no listeners or browser/host permissions, makes no network
requests, does not activate the inactive background worker, and does not
change the installed fail-closed ClamAV opening gate, quarantine behavior,
native handoff or saved user choices. Browsers that cannot expose
`Content-Disposition` under separately authorized APIs cannot supply this
evidence here. The dedicated `tests/pdf-response-attachment.test.mjs`
regressions run in the shared `npm test` suite and in GitHub CI.
