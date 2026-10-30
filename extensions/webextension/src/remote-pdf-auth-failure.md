# Remote PDF authentication failures (opener-0766)

The passive remote-pdf-auth-failure.js module defines a correlated, fail-closed
authentication-failure handler for a future explicit Scan This PDF download.
It is deliberately separate from the remote-fetch consent gate (opener-0763)
and the in-flight browser download adapter (opener-0764, PR #522), so this task
does not duplicate or modify either integration.

## Recognized failures

Only an independently authenticated browser adapter may submit these events:

- HTTP 401 -> sign-in required.
- HTTP 403 -> access denied.
- HTTP 407 -> proxy authentication required.
- Browser downloads interruption SERVER_UNAUTHORIZED -> sign-in required.
- Browser downloads interruption SERVER_FORBIDDEN -> access denied.

The input is exactly {requestId, downloadId, kind, code}. A browser download
interruption must have a nonnegative numeric downloadId. A pre-download HTTP
failure can set downloadId to null. Every event requires a bounded, opaque
requestId. Unknown responses (including redirects, HTTP 404/429/500 and
general connection errors) are **not** mislabeled as authentication failures;
the ordinary failed-transfer gate must still reject them.

The trusted coordinator must supply its own synchronous
readVerifiedRemotePdfTransfer({requestId, downloadId}) callback and return
exactly {requestId, downloadId, selectionId, verified: true}. An untrusted page
claim, an arbitrary HTTP response object, a guessed download identifier, or a
reported status code cannot by itself establish trusted provenance. The
coordinator must independently bind browser response/download events to the
current explicit user request and selected PDF.

## Failure behavior

Verified failures permanently block their request ID within this handler.
isBlocked(requestId) returns true for a failed request (and for invalid IDs
or a disposed handler). **A false result is not scan authorization:** native
scanner, transfer completion and opening gates remain independently required.

The one-time optional notifyRemotePdfAuthenticationFailure(safeResult)
callback receives a frozen, path-free status with a generic explanation:
sign in using the browser, check site access, or authenticate the network
proxy, then start a **new** explicit Scan This PDF attempt. There are no
automated authentication retries, credential prompts, cookie/header
inspection, login requests, URL logging, background downloads, saved
passwords, or silent failure recovery. A throwing notification cannot undo
the block; duplicates do not redisplay the notice or reset it. The handler
has a bounded cache (256 request IDs) and an idempotent dispose() method.

## Integration prerequisite

The shipped browser extension remains inactive and has no registered network
response observer, new permissions or native host transport. A separately
reviewed trusted browser adapter must supply authentic download IDs/HTTP
responses and use the block to veto a failed transfer before any native
scan/file opening. Its acquisition path must still enforce consent and
permission freshness, reject unauthorized redirects, protect any partial
download, and preserve the user's preferred PDF app. This module never
opens the browser login flow or retries; doing so without a fresh user action
could leak credentials or fetch another remote resource.

The 12 Node regression cases in
tests/remote-pdf-auth-failure.test.mjs verify supported codes, provenance,
mismatches, denial and replays, privacy, hostile objects, cache bounds,
notification failure, and unchanged browser/scanner boundaries. Existing
npm test / scanner-tests CI discovers this test suite automatically.
