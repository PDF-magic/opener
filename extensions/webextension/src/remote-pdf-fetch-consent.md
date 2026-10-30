# User consent before remote PDF acquisition (opener-0763)

The new remote-pdf-fetch-consent.js module defines an opt-in, **per-request
consent gate** for the existing explicit Scan This PDF metadata contract.
Neither importing nor creating the gate contacts a website, requests browser
permissions, connects to native code, alters scanner settings, or opens a PDF.

The caller provides the seven-field explicit PDF scan request (version, request
ID, source, tab/frame IDs, opaque selection ID, direct-user-action claim).
A separately reviewed authenticated coordinator must supply an own
remotePdfFetchReady: true capability and three own methods:

1. readVerifiedRemotePdfSelection(reference) returns **synchronously and
   without network access** the exact fields tabId, frameId, selectionId,
   resourceId, siteOrigin, verified: true, permissionGranted: true.
   resourceId is a bounded opaque resource identifier, not a URL or file path.
2. promptForRemotePdfFetchConsent(notice) must display a user-visible consent
   dialog containing the canonical HTTPS siteOrigin, the fact that a remote PDF
   will be requested/downloaded, and Allow/Decline controls. It must return a
   Promise resolving to exactly true **only for an explicit affirmative choice**.
   The gate calls this callback synchronously in the initiating action handler,
   before its first await. A preexisting browser permission or saved setting is
   not equivalent to consent.
3. requestVerifiedRemotePdfFetch(reference) is called **only after consent
   and a fresh identical selection and permission check**. It receives an
   immutable opaque selection/resource identity, original tab/frame, source,
   attempt ID and canonical HTTPS origin; never a source URL, local path, page
   bytes or purported clean verdict. The callback must resolve to an accepted
   acknowledgment, never a claimed scan result.

Consent is not persisted, reused or shared across attempts: the request ID is
one-shot even on denial/errors, concurrent replays fail, and dispose invalidates
pending approvals. Wrong or changed document/resource/origin, revoked permission,
invalid identity, malformed inputs and ambiguous prompt responses fail closed.
Only canonical HTTPS origins are in scope; HTTP, local, embedded-credential,
path-bearing and malformed origins require separate review.

**Integration prerequisite:** The installed extension is intentionally inactive
with no site grants, browser event handlers or remote-fetch native coordinator.
This task establishes the enforceable ordering contract; it does NOT show a
dialog or fetch a remote PDF in the current shipped extension. A future trusted
browser adapter must show the actual consent UI, attest the real user gesture,
authenticate the current document and site permission, prevent redirects to
unapproved origins, prefer existing verified local copies where applicable,
and safely stage remote bytes for the native scanner. The native integration
must independently enforce canonical file integrity, current ClamAV
signatures, quarantine, scanner outcomes, mandatory scan-before-open and
the user's selected PDF application. A fetch acknowledgment never authorizes
scanning or opening.

The WebExtensions tests/remote-pdf-fetch-consent.test.mjs regression suite
covers approval ordering, refusal, missing prompts, unsupported sites, missing
permissions, stale resources, races, one-shot IDs, cancellation, hostile
objects, and unchanged scanner/browser boundaries. Existing npm test and
scanner-tests GitHub CI automatically include these tests.
