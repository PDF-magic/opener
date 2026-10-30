# Cleanup policy for temporary Scan This PDF acquisitions (opener-0776)

`createExplicitPdfTemporaryCleanup(coordinator)` implements the **opt-in,
fail-closed cleanup gate** for an application-owned temporary PDF lease after
a trusted explicit Scan This PDF request. Its `cleanup({request, downloadId,
leaseId})` method receives only the existing seven-field explicit request,
a browser-owned nonnegative download ID and an opaque lease ID. **No file path,
URL, signed token, PDF bytes or user-selected destination crosses the API.**

The trusted native coordinator must independently authenticate the active
scanner session and own the lease, then provide:
- `nativeTemporaryCleanupReady: true`;
- `readCurrentSelectionId()` and a synchronous, network-free
  `readVerifiedTemporaryPdfLease(reference)` giving strictly structured
  identity, ownership, lifecycle and cleanup-policy evidence;
- `removeVerifiedTemporaryPdfLease(reference)` returning a Promise only
  after securely removing that **same, owned private lease**;
- `verifyTemporaryPdfLeaseRemoved(reference)` independently confirming
  its absence (also a Promise).

Cleanup follows three policy branches:

1. **Retained:** `user-selected-download`, `existing-local-pdf` and
   private leases with policy `retain`. The extension never deletes a
   user-chosen `downloads.download({saveAs:true})` destination or an
   original, regardless of scan outcome.
2. **Deferred:** an application-owned private lease whose scan is active,
   native opening is active, quarantine remains held, or whose state is not
   `retired`. Future verified lifecycle updates may permit reevaluation.
   In particular, a clean result does NOT mean the file can be deleted before
   the separately authorized **Open Scanned PDF** workflow finishes.
3. **Removed:** only an exactly matching, fully verified, app-owned private
   lease with policy `delete-after-use`, state `retired`, no active scanner
   or opening and no quarantine hold. A second verified read is performed
   immediately before submitting removal. The operation is reserved once
   before invoking native deletion; retries after uncertain outcomes are
   prohibited. The caller receives `removed:true` only after a matching
   native removal acknowledgement **and a separate confirmed absence check**.

Native removal must use its own app-private lease database and secure
filesystem ownership checks, validate no symlink substitutions or inode
changes, and never follow untrusted browser filename/path references.
A Boolean on a JavaScript coordinator is not filesystem authentication.
If any proof is missing or stale, the gate fails closed. `dispose()`
invalidates pending results and future calls; a cleanup callback already
submitted must itself be safely idempotent on the native side.

The **production prerequisite** is an independently authenticated native
lease manager for explicit PDF temporary downloads. The existing browser
acquisition uses `saveAs:true` and does not establish an app-private lease;
the shipped WebExtension background is still intentionally inactive.
This component therefore performs no deletion today without future trusted
integration. It grants no permissions, uses no browser filesystem deletion,
and cannot authorize a scan, opening or quarantine bypass. Existing scanner
policy, timeout/size controls and saved user settings are unchanged.

The dedicated regression suite tests verified deletion, user-file
retention, active scanning/opening/quarantine, source and lease mismatches,
forged metadata, deletion and verification failures, async disposal,
privacy, and unchanged browser privilege gates. It runs in the default
`npm test` matrix and as a dedicated scanner CI step.
