# Local `file:` PDF identification regression (opener-0755)

`tests/pdf-local-file-urls.test.mjs` exercises the shared WebExtensions PDF
candidate detectors with local `file:` URLs rather than assuming an HTTP
response. It builds a small, synthetic one-page PDF in an isolated temporary
directory, obtains its real URL using Node's `pathToFileURL`, and supplies
that URL to the existing passive metadata classifiers:

- `detectPdfCandidate({ url })` for the shared PDF path hint.
- `detectPdfNavigation({ tabId, frameId: 0, url })` for trusted top-frame
  navigation metadata.
- `classifyPdfDocumentResource({ type: "main_frame", tabId, frameId: 0, url })`
  for the document-only resource gate.

The regression covers local URLs with spaces, Unicode filenames, mixed-case
PDF suffixes, percent-encoded periods, query strings, fragments, and
`file://localhost`. It rejects misleading suffixes, PDF mentions confined
to query/fragment text, encoded separators, malformed escaping, invalid
browser tab/frame context and non-document resources. A non-PDF MIME
declaration cannot be used to override the normal candidate-detection
safeguards.

**Identifying a `file:` PDF candidate does not open or scan the file.**
The test deliberately verifies that the result remains only a URL-path hint
even when its temporary fixture is removed. Classifiers return immutable,
path-free flags, never private local paths or permission to scan or open.
The extension's background remains inert, and no browser `file:` access
permission, native messaging, file reads, launch, scanner override or user
configuration change is introduced.

This tests the **identification** portion of the §12.1 checklist. Actual
browser opening and native scanner handoff cannot be claimed until a
separately reviewed browser event/permission integration is installed. The
installed native ClamAV, signature freshness, file integrity, quarantine and
verified scan-before-open rules remain mandatory.

The existing `extensions/webextension/package.json` `npm test` command
automatically discovers `tests/pdf-local-file-urls.test.mjs`, so GitHub's
`scanner-tests` CI already runs this regression without a redundant workflow.
