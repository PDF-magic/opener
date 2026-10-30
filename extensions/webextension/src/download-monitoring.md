# Shared download-monitoring module (opener-0570)

The reusable, dependency-free `src/download-monitoring.js` module provides
`subscribeToDownloadEvents(downloadsApi, onEvent, { onError }?)` and
`normalizeDownloadEvent(kind, payload)` for browser download event sources.

A trusted future extension entry point must explicitly supply a browser's
`downloads` API after separately reviewed permission and activation work.
The subscriber attaches `onCreated`, `onChanged`, and `onErased` handlers,
and returns an idempotent unsubscribe callback. No listeners are registered
on import. Registration failures roll back already attached listeners.

Events are shallow, frozen records. They contain only the kind and numeric
browser download ID, plus bounded untrusted filename, MIME, state, danger and
error strings when supplied. `onChanged` forwards only each field's
`current` value; `onErased` uses the numeric ID supplied by WebExtensions.
It never forwards download URLs, referrers, headers, cookies, bytes or other
browser data. Browser `danger` and `state` values are **not** ClamAV
verdicts or permission to open a PDF. Consumers must not use these events
as evidence of file safety.

This module does **not** acquire download permissions, query browser history,
access native messaging, classify PDFs, scan or open files, or activate any
background listener. The existing inert background entry point and
browser-specific manifest work remain separate. Production download
monitoring requires independently reviewed permissions and wiring; the
native scanner's mandatory signature freshness, file-integrity, quarantine
and application-handoff checks are unchanged.

The existing CI `npm test` step automatically executes
`tests/download-monitoring.test.mjs` on Node.js 22. The tests cover event
normalization, privacy, correct browser ID handling, opt-in activation,
listener cleanup and failure isolation.
