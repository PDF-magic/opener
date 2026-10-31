# Reject late PDF navigation observations as interception gates (opener-0782)

**Decision:** PDF Magic Opener must **not** rely on APIs that only observe
navigation after content has loaded, or on nonblocking lifecycle
notifications, to prevent PDF rendering or opening. The extension remains
inactive. A PDF URL notification is never a ClamAV verdict.

The existing [pre-render event timeline](pdf-pre-render-navigation-events.js)
(opener-0779) distinguishes potentially early and late event phases. The
[per-browser interception point assessment](pdf-interception-point-assessment.js)
(opener-0781) distinguishes possible matching-network-request blocks from a
native scan-before-open interlock. This task adds a small, **passive rejection
policy** joining both decisions in
[pdf-preload-interception-trigger.js](pdf-preload-interception-trigger.js).

## Event policy

| Observed browser event | Relative timing | May start an enforceable native PDF scan-before-render gate? |
| --- | --- | --- |
| webNavigation.onBeforeNavigate | Potentially before navigation | **No.** Notification only, not a request veto |
| webRequest.onBeforeRequest (main_frame) | Before a matching network request | **Conditional candidate only.** Firefox blocking webRequest requires host/API grants; normal Chrome/Edge MV3 lacks general blocking except the enterprise policy-installed exception; Chromium forks require version checks; Safari has no established equivalent blocking listener |
| webRequest.onBeforeRedirect | Redirect response | **No.** Final PDF identity and next response are unverified |
| webRequest.onHeadersReceived | Headers, potentially before response body | **No automatic authorization.** A MIME hint is not full bytes or proof that rendering can be held. Firefox response filtering requires separate permissions and safe stream ownership |
| webNavigation.onCommitted | Navigation commit | **No.** The browser might already be processing content; not a synchronous network veto |
| webNavigation.onDOMContentLoaded | After document DOM load | **No.** Too late for a reliable before-render gate |
| webNavigation.onCompleted | Navigation complete | **No.** Too late |
| webNavigation.onErrorOccurred | Navigation failure | **No.** Not a veto or complete PDF proof |
| webNavigation.onHistoryStateUpdated / onReferenceFragmentUpdated | Existing document changed | **No.** Not a pre-response veto |
| webRequest.onCompleted | Request complete | **No.** No longer a before-body gate |
| downloads.onCreated / onChanged / onErased | Download already started or changed | **No.** Download lifecycle observation cannot stop an inline viewer or operating-system open before loading |
| tabs.onUpdated | Tab update notification | **No.** Does not synchronously hold the response |

There is no guaranteed ordering between webNavigation and webRequest
notifications. An early observation does **not** demonstrate effective
webRequestBlocking permission, an installed enterprise configuration,
a verified PDF, or an authenticated scanner connection.

The pure exported function
assessPdfPreLoadInterceptionTrigger(browserId, event, details) calls the
existing reviewed pre-render event classifier, requires its verified
main-frame event shape, and applies the separate browser point assessment.
All results are immutable and contain no page URL or headers. The only
potential blocking event in this policy is webRequest.onBeforeRequest for
a browser with a documented **conditional** blocking point. A true
conditionalPreRequestBlockingCandidate is **not** permission or proof:
every result sets effectiveBlockingPointVerified, permissionVerified,
pdfBytesVerified, nativeScanVerified, mayInitiateAutomaticInterception,
allPdfOpeningPathsBlocked, authorizesScan and authorizesOpen to **false**.
Unknown or malformed events fail closed, and the late/nonblocking set is
rejected *before* examining potentially sensitive page details.

## Required production safeguards

A separately reviewed future integration must verify genuine opt-in user
consent and revocable site permission, exact browser/version support, an
actual synchronous request veto, correct PDF and redirected-resource
identity, complete byte capture, bounded timers and service worker
recovery, trusted ClamAV signatures and clean scan, quarantine, and the
user's selected application and user preferences. Unmatched HTTP requests,
cached/inline documents, blob/data/file sources, other extensions and Finder
can bypass browser-network mechanisms. Never claim all PDF opening paths
are intercepted. Never turn a late event into a new automatic download or
a fallback opening path.

No manifest changes, browser listeners, webRequestBlocking, network calls,
scan calls or native permissions are introduced. The installed extension
still has an inert background. The 15 regression groups in
tests/pdf-preload-interception-trigger.test.mjs run under WebExtensions
npm test and the scanner-tests CI job, checking late-event rejection,
browser-specific conditional candidates, hostile inputs, privacy and
unchanged scanner safety and user preferences.
