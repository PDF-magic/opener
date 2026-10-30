# Managed download, scan and open where strict interception is unavailable (opener-0718)

This is a **separate, explicitly user-initiated PDF Magic workflow**,
not a claim that an extension can block browser-owned PDF opening.
The reusable module is download-managed-open.js in the shared
WebExtension source. It exports createManagedDownloadAndOpenGate() and
createManagedDownloadAndOpenAction(root, coordinator, gate).

## Browser applicability

See the [browser-opening support matrix](../../../docs/download-opening-browser-support.md)
and [interception research](../../../docs/browser-interception-apis.md).
Brave, Chrome, Chromium, Edge, Vivaldi, Opera, Arc and Firefox lack a
documented **universal standard-extension pre-open veto**. Safari's
specific ability is unverified and must be treated as unavailable
until independently tested. This managed alternative is suitable for
these contexts, but is **not automatically activated** in any of them.
The coordinator must derive managedWorkflowRequired: true from its
OWN verified browser/profile policy, not user-agent strings, page
content or any browser-provided claim of scan safety.

The shared WebExtensions package is intentionally inactive in all
nine browsers. Neither its popup nor background is changed. Its
manifest does not gain opening, native messaging or network permissions.

## Required independently trusted native coordinator

A future coordinator must independently authenticate the extension
and native session, verify user consent, and own:

1. A previously consented and approved download resource indexed by
   an opaque managedRequestId (ASCII letters, digits, underscore and
   hyphen, 1–80 characters). The coordinator MUST resolve the
   resource inside the authenticated native session, not from a URL,
   local path, browser MIME or filename, origin, destination application,
   cookies, page data or asserted clean status supplied to this adapter.
2. Trusted managedWorkflowRequired: true and
   nativeManagedWorkflowReady: true availability, and an async method
   requestManagedDownloadAndOpen({managedRequestId}). The readiness flags
   are **not** native authentication or scanner evidence. A successful
   acknowledgment must be exactly
   {accepted: true, managedRequestId: <same ID>}, and means only a
   native request was queued.
3. Safe, explicitly authorized acquisition of the chosen PDF, without
   SSRF, unsafe redirects, credential exfiltration, unbounded responses,
   unsolicited URL access or unsafe filesystem destinations. Never
   disable the browser's own dangerous-download warnings.
4. Mandatory complete ClamAV scanning with current signatures, installed
   Built-in policy, independently verified canonical file identity and
   unchanged bytes, macOS quarantine retention, and the user's selected
   verified PDF application. Recheck every gate at the final native
   handoff. Malicious, suspicious, interrupted, timed-out, cancelled,
   missing, incomplete, failed or changed-file outcomes **must not open**.
5. Idempotent native request handling and job reconciliation after
   a worker restart, native disconnection or unknown outcome. No
   automatic resubmission or double opening for an uncertain job.

The installed native messaging host is still **transport-only** and
responds trusted-scan-coordinator-required. Therefore this PR adds
only an **opt-in, independently tested presentation and request
boundary**, NOT a functioning download or scanner. Native coordinator
implementation and real browser acceptance tests are hard
prerequisites before this UI can be enabled in production.

## Explicit action and one-request-per-session contract

- A trusted extension-owned UI constructs ONE
  createManagedDownloadAndOpenGate() for the authenticated session,
  reusing it across all views. The gate supports at most 256 distinct
  pending or previously attempted opaque request IDs without eviction.
- After the coordinator verifies the source record, browser policy
  and consent, action.offer(managedRequestId) displays an actual
  **Download, Scan & Open with PDF Magic** button and an explanation:
  only this managed request is gated; all other browser and system
  opening paths remain independent.
- A genuine browser-generated click, including keyboard and accessible
  activation, disables the button **synchronously**. The shared gate
  reserves the ID before invoking the coordinator with the frozen
  one-field object {managedRequestId}. It never passes arbitrary
  paths, URLs, selected apps, cookies, verifier flags or PDF bytes.
  Synthetic clicks, invalid IDs, unavailable native policy and
  duplicate requests are rejected.
- A correlated native queue acknowledgment produces only
  status: request-submitted. It does NOT prove a download was started,
  completed, scanned, or opened. Every return state keeps
  downloadVerified: false, scanVerified: false,
  authorizesOpen: false and opened: false. Failed, missing, malformed,
  miscorrelated and thrown native results display a fixed unavailable
  message without private data. **All attempts reserve the ID even
  when the response fails:** the native job could already exist.
- clear() and dispose() unregister click handlers and discard stale
  async results; neither cancels native work nor clears the shared
  reservation. The owning native session must separately reconcile
  and cancel jobs before disposing the gate.

## Independent opening paths are not controlled

Browser download UI, auto-open settings, inline PDF rendering, Finder,
external applications and other extensions remain outside this
particular managed route. Offering it never silently changes PDF
preferences or intercepts unrelated opening. **Do not claim that all
browser PDFs are scanned before they can open.** Stronger interception
requires independently researched browser/OS APIs, explicit permission
and user review, and live acceptance tests. See the
[interception API assessment](../../../docs/browser-interception-apis.md).

The 15 Node regression tests in
extensions/webextension/tests/download-managed-open.test.mjs are picked
up by the existing WebExtensions npm test / scanner-tests CI job. They
cover user intent, ID-only submission, deduplication, input validation,
native readiness revocation, callback errors, native correlation,
stale replies, capacity, listener cleanup and unchanged permissions.
