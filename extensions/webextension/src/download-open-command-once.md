# Prevent duplicate download opening commands (opener-0706)

`createDownloadOpenCommandGate()` provides a passive, session-owned one-shot
gate for the trusted native download-scanning coordinator. A single gate must
be constructed **once per authenticated native scan session** and reused
across all trusted extension UI views, callback retries, and Open After
Scanning actions. It is not installed automatically in the production
WebExtension popup/background, which remain inactive.

Use `await gate.requestOpenOnce(scanRequestId, issueOpenCommand)` only after
the independently authenticated coordinator has verified that the user's
opening intention belongs to its locally owned scan request. The bounded
scan request ID is an ASCII correlation key, **not authentication, file
identity, a browser download ID, a claim that scanning succeeded or a
permission to open**. The injected callback takes **no arguments**, so the
gate cannot pass attacker-controlled paths, URLs, metadata or safety flags.
The trusted coordinator must own all actual scan and open state.

The first valid request ID is reserved synchronously **before** invoking
the callback or awaiting any Promise. A second request with the same ID is
rejected as `duplicate`, including concurrent/reentrant callbacks, repeated
button presses, and retries after an ambiguous failure or acknowledgement.
A refused, malformed, thrown, timed-out or successful native command does
**not** release its reservation, because the native side may already have
opened or be processing the PDF. Reusing browser download IDs, rerendering a
button, or reopening a tab must not release a scan-session opening
reservation. The gate holds a bounded maximum of 256 IDs and **never evicts**
old reservations to admit a new command. Capacity exhaustion fails closed.
`dispose()` makes the gate permanently unusable and invalidates pending
acknowledgements. A later native scan session must have a separately owned,
non-reused scan request ID and its own gate.

Return values are frozen and contain only `status`, `scanVerified: false`,
`authorizesOpen: false`, `opened: false`. The possible statuses are
`unavailable`, `duplicate`, `capacity-exhausted`,
`command-rejected`, and `command-submitted`. Even the final status means
only that the injected callback acknowledged a command, **never** that the
PDF was scanned, approved or launched. Native error text is not logged or
returned.

## Relationship to neighboring tasks and required safety

- The native Finder opener already deduplicates repeated macOS open events
  via its canonical-path `received` set, and `test-brave-pdf-opener.py`
  exercises that behavior. Merged PR #337 preserved the native regression
  and CI registration.
- Merged PR #456 prevents duplicate **scan submissions** by browser
  download ID. A scan request is not a command to open a verified file.
- Concurrent PR #468 (opener-0704) introduces an **opt-in user-interface
  action** that disables repeated clicks within one button instance.
  A session-level gate remains necessary when several views or retries can
  call the same coordinator. This task does not modify PR #468, its original
  description or branch. A future native integration must use the gate at
  the shared native boundary, not create a fresh gate per button.
- The installed native messaging host is still transport-only. Real
  opening requires a separately authenticated coordinator, a completed
  clean ClamAV verdict, verified fresh signatures, current file bytes and
  canonical filesystem identity, quarantine retention and the user's
  configured PDF application. These checks and cancellation policy remain
  enforced by the existing `scan-and-open.py` implementation; this
  JavaScript gate **never authorizes or performs opening**. Scanner results,
  popup configuration, permissions and all user preferences stay untouched.
  Real native delivery must also deduplicate each request after a restart
  or reconnection, since this gate is deliberately in-memory.

The 13 tests in `tests/download-open-command-once.test.mjs` are discovered
by the existing WebExtensions `npm test` step under `scanner-tests` CI.
They verify multi-view, concurrent, reentrant, failed, duplicate and
capacity-exhausted requests; disposal, invalid IDs, metadata privacy,
acknowledgement semantics and inactive extension startup.
