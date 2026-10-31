# Handle browser Back during optional PDF interception (opener-0790)

**Scope:** one passive holding-entry lifetime contract. The current shared
WebExtension background is deliberately inactive; there is no deployed holding
screen, automatic interception listener, or authenticated native interception
coordinator. This module does **not** implement those prerequisites.

## Expected behavior

When the user presses Back while a future, separately authorized PDF holding
screen is showing, the browser must traverse its history normally. The
extension must not invoke history.back(), insert a replacement or additional
history entry, redirect to the holding screen again, resume the pending scan,
or automatically reopen the PDF. The currently held scan must be invalidated
**before** asking the trusted native coordinator to cancel it. Failed or
asynchronous cancellation cannot make the old result valid again.

createPdfInterceptionBackNavigationGuard creates a one-entry session with
a browser-tab ID, opaque holding-entry ID, and a *provided* cancellation
callback. A trusted future coordinator may deliver a normalized, verified
top-frame history-leave record: tab ID, frame ID zero, leaving entry ID,
direction back or forward, and verified: true. The record is checked exactly;
no raw URLs, headers, source documents or browsing history are recorded or
returned. A browser webNavigation forward_back qualifier alone is **not**
sufficient to determine direction or authenticity.

On a verified Back event, the guard invalidates its holding session first,
requests cancellation at most once and returns a frozen, URL-free decision:
skipHoldingRedirect: true, historyMutationRequested: false,
navigationRequested: false, and both authorizesScan and authorizesOpen false.
If the user later presses Forward or BFCache restores the old holding entry,
onPageRestore() remains stale; the scan is not replayed. An unrelated tab,
subframe, forged gesture or unexpected event cannot cancel the tracked session.
Every exit and disposal is idempotent.

When reliable direction observation is unavailable, the future holding page
must call onPageExit() on pagehide/tab teardown: that invalidates the
session without assuming whether the user pressed Back. It must also check
isCurrentHoldingEntry() before consuming any asynchronously delivered
scanner result. The boolean is a **staleness check only**, not a clean verdict
or permission to open. If a new page instance is created, it must not infer
consent from a previously held history entry.

## Prerequisites / browser limitations

Actual automatic handling still requires separately reviewed opt-in and
browser-specific blocking support, the holding screen (opener-0785), original
URL preservation (opener-0787), the verified native scan handoff
(opener-0784), and scan/open lifecycle coordination (opener-0788). A pagehide
or history observation is not a pre-render veto. Some browser-internal PDF
viewers and history paths cannot expose a cancellable navigation event. No
browser-wide blocking guarantee is implied. Existing ClamAV scan gate,
quarantine, signature freshness, verified file identity and user-selected
PDF application remain authoritative.

The 11 Node regression tests cover Back, Forward/BFCache stale replay,
fallback exit, idempotent cancellation, asynchronous failures, reentrancy,
mismatched/hostile event records and permission-free behavior. The existing
WebExtensions npm test glob executes this suite in required CI.
