# Handle browser tab closure during scanning (opener-0791)

`createTabScanClosureGuard(tabs)` is a passive, opt-in adapter for a future
privileged browser coordinator. The injected `tabs.onRemoved` must be the
browser-owned event source, **not** a page message, content-script claim, or
untrusted scan result. This guard does not obtain permissions, register a
listener on import, initiate automatic interception, create native sessions,
scan a PDF, navigate a tab, or choose a PDF-opening application. The installed
WebExtension background remains deliberately inactive.

After the future authenticated coordinator has verified an actual originating
tab ID and the native scanner has accepted a job, it may call
`track(tabId, cancelScan)`. Each native-owned callback MUST immediately cancel
and reap its corresponding scanner process group, including any temporary
resources owned by that job. An `onRemoved` event revokes all tokens for that
tab **before** invoking their cancellation callbacks synchronously. A closed
tab ID cannot be registered again in the same guard lifetime, even if closure
was observed before `track`. Other tabs' scans continue independently.
Completed jobs must be released; disposal cancels all remaining jobs and
removes the listener. Invalid tab-removal events or excessive closed-ID
tracking invalidate the entire guard rather than silently retaining scans.

The coordinator MUST verify that the browser's tab/document identity is still
current when a job is associated with a tab and again before any native-open
handoff. `isActive(token)` and `receive(token, pending)` prevent a late clean
result from being consumed after tab closure, release, or disposal;
`receive` returns a non-authorizing `unavailable` object on those paths.
A live return is still **unverified native data**: no token, event, callback,
or result from this adapter certifies scanner safety or authorizes opening.
The coordinator must check `isActive` immediately before accepting a verdict
and separately enforce native identity, signature freshness, quarantine, and
scan-before-open policies.

**Prerequisite:** the current extension has no active automatic interception
pipeline or authenticated native scanner coordinator. A true browser
integration must inject verified `tabs.onRemoved` events, associate scan jobs
with the correct top-level tab, check tab existence before registration, and
wire cancellation to native jobs. Browser termination can also skip tab events;
existing native Port/browser closure guards and native process-lifetime
watchdogs must cover that case. Closing the browser tab must never implicitly
reopen it or restore an expired/credential-bearing URL. This task does not
add the missing integration or weaken user customizations.

`tests/tab-scan-closure.test.mjs` is included by the existing WebExtensions
`npm test` wildcard and its GitHub `scanner-tests` CI job. It covers
per-tab isolation, multiple pending jobs, pre-registration closure, duplicate
removals, late scanner results, disposal, malformed events, cleanup failures,
registration races, bounded memory, and a side-effect-free import.
