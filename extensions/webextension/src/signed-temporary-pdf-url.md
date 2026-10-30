# Signed temporary remote PDF URLs (opener-0769)

The passive signed-temporary-pdf-url.js module defines a one-shot,
short-lived, **credential-sensitive** handoff boundary for explicitly
requested Scan This PDF operations. Signed URLs may use AWS-style signatures,
Azure SAS tokens, repeated query fields, opaque path tokens or other schemes.
**Do not infer a signature or expiration from query parameter names.** A URL
is a bearer credential even when its signature format is unknown.

## Required trusted evidence

The installed WebExtension is deliberately inactive. A separately reviewed
and authenticated browser coordinator must provide its own methods:

- readVerifiedSignedPdfSelection(reference): synchronous, side-effect-free
  source verification that yields precisely requestId, tabId, frameId,
  selectionId, resourceId, url, siteOrigin, expiresAtMs, verified:true,
  signatureVerified:true, permissionGranted:true. The URL must be the EXACT
  current authenticated selection, the signature must be independently
  verified by the source integration, the HTTPS origin must match the selected
  host, and the expiration deadline must be derived from verified source
  metadata, **not** an untrusted Expires, X-Amz-Expires or SAS query value.
- consumeVerifiedSignedPdfConsent(reference): Promise<true> **only when**
  the original user-visible approval was actually shown and bound to this
  exact request, resource, site, and one-shot consent record. The boolean
  userInitiated input alone never proves a browser gesture. The callback
  must atomically consume consent, not reuse site permissions as consent.
- handoffVerifiedSignedPdfDownload(reference): Promise<{accepted:true}> for
  a separately reviewed, permissioned browser adapter. This is the ONLY
  callback that receives the original URL, and it receives it without
  decoding, sorting, trimming, re-encoding, dropping repeated query fields
  or discarding signature-sensitive percent-encoding. It must independently
  enforce site access, redirect provenance and revocation, never log or
  persist URLs, and stage the bytes for mandatory native scanning.

Every request uses the versioned explicit-pdf-scan-request.js metadata and a
one-time request ID. Before consuming consent, a trusted source must be
verified and have more than 30 seconds remaining. After consent, the guard
**re-reads the current source and verifies byte-for-byte URL, resource,
tab/frame, selection, origin, signature, permission and expiration again**,
and enforces the same remaining-time threshold using the local clock.
Unknown, expired, near-expiry, ambiguous or changed resources fail closed.
The user must obtain a new link and consent again. There is no automatic URL
refresh, retry, token substitution or silent re-download.

The guard intentionally accepts canonical HTTPS URLs only, without embedded
credentials, fragments, unescaped whitespace, control characters, malformed
percent encodings, local schemes or URL normalization ambiguity. This is a
safe subset; noncanonical links require a separate reviewed adapter. A
strictly verified signature can be in the path as well as the query.

Results are frozen, credential-free status records; even a successful
handoff is **NOT** a completed download, clean scan or authorization to open.
A throwing callback cannot leak private query tokens into errors. Calling
dispose() invalidates pending consent, although the trusted adapter must
separately cancel an already-started browser download on later revocation.

## Integration and testing

This contract is separate from the in-flight supported downloads transport
PR #522 and cross-origin gate PR #525, and complements the merged per-attempt
consent PR #521 and expired-link handler PR #524. Those adapters are not
rewritten by opener-0769. The current manifest has no host permissions and
the background remains inert. No native or browser transport is activated.

The independently reviewed integration must require the consent gate and
expiry handler on every applicable operation, enforce fresh browser-granted
site/download permissions, require trusted origin-bound redirects, protect
partial downloads, revalidate local file identity, and retain mandatory
ClamAV, signature freshness, quarantine, scan-before-open and user-selected
PDF application safeguards.

tests/signed-temporary-pdf-url.test.mjs contains 15 Node regression groups
for exact query/path preservation, URL secrecy, expiry and consent ordering,
signed-source provenance, site-permission revocation, races, retry prevention,
malformed and hostile inputs, and unchanged extension/browser policy. The
existing npm test wildcard includes the suite in scanner-tests GitHub CI.
