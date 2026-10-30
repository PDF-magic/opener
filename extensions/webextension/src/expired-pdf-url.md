# Expired document URL handling (opener-0767)

The passive expired-pdf-url.js module handles an explicit Scan This PDF
attempt when its current remote document link has expired or become permanently
unavailable. This is a **failure veto**, not a download resolver, a live HTTP
observer, or permission to access a newer document. Nothing happens on import.

## Evidence and classification

The trusted browser integration supplies a four-field failure record:
{requestId, downloadId, kind, code}. A response can precede download ID
allocation (downloadId: null). Only these cases are recognized:

- HTTP 410 Gone: the original document resource is permanently unavailable;
  advise returning to the website for a new link.
- HTTP 403 or 404: **only** classify as expired when the coordinator has
  separately verified that a trusted resource expiration deadline has passed.
  A bare 403 may be an authentication/permission failure; a bare 404 may be a
  missing document. Neither proves URL expiration.
- Explicit {kind:"expiry", code:"DEADLINE_PASSED"}: **only** when independently
  verified expiration metadata confirms expiry. The event claim alone is not
  sufficient.

HTTP 401/407 and browser SERVER_UNAUTHORIZED/SERVER_FORBIDDEN remain handled
by the authentication-failure contract (opener-0766). Other HTTP statuses,
unknown browser interruptions and suspicious input do not become expired URL
verdicts.

The authenticated coordinator supplies an own synchronous,
network-free readVerifiedRemotePdfUrlSource({requestId,downloadId}) method.
It must return precisely {requestId, downloadId, selectionId, resourceId,
expiresAtMs, observedAtMs, verified:true}, where the identifiers are bounded
opaque references to the *currently selected* PDF, and the time values are
trusted nonnegative safe-integer epoch milliseconds (expiresAtMs can be null
only for status 410). **Never derive the expiration time from a page's query
string or trust a browser-provided page response without independent
provenance.** The coordinator must verify the current selection, resource,
access grant and response identity itself.

## Failure behavior and integration requirements

A verified expired/gone URL permanently blocks its request ID within the
handler, before optional one-time notifyExpiredPdfUrl(safeResult) guidance.
Notifications are sanitized and contain no source URL, query token,
credentials, filesystem path or document bytes. They direct the user to
reload the website, select a **new** document link and make a **new explicit
Scan This PDF request with fresh consent**. No automatic refresh, URL replay,
HTTP retry, download or scanner call occurs. Duplicate notices do not reset
the block; dispose permanently invalidates the handler.

isBlocked(requestId) is only a negative veto. False does **not** imply a
verified PDF, a valid download, an up-to-date ClamAV scan, or permission to
open anything. A trusted adapter must consult the veto before any subsequent
scan/open operation, independently enforce the full native scan-before-open,
signature freshness, integrity, quarantine and browser warning policies, and
preserve all user customization.

**Prerequisite:** The shipped WebExtension background remains inert, without
HTTP listener or native coordinator. The in-flight download acquisition PR
#522 implements a different, dormant transport contract. This scoped task
defines the expiry handler and tests without activating network access or
modifying the acquisition PR. A separately reviewed, authenticated browser
adapter must wire real response observations to this handler and honor its
result. The module cannot deduce expiration from a URL alone.

The 13 Node regression test groups under
tests/expired-pdf-url.test.mjs cover HTTP and signed-link expiry boundaries,
independent provenance, 403/404 ambiguity, authentication separation,
replay prevention, path/token secrecy, hostile inputs, bounded failure cache,
cleanup and unchanged manifest/scanner policy. The existing WebExtensions
npm test wildcard runs them in scanner-tests GitHub CI.
