# Isolate simultaneous PDF tab scans (opener-0792)

This passive registry is for future opt-in automatic PDF interception. The
shipped browser background remains inert: it does not intercept PDFs, register
listeners, change permissions or open documents.

A **trusted browser adapter** must authenticate the tab ID from a real
top-level browser event, mint a unique opaque request ID, and pass a native
scan cancellation callback to createPdfTabScanRegistry().begin. The registry
does not accept URLs, paths, PDF bytes, scanner verdicts, or user settings.

Every tab has its own immutable ticket. Scans can overlap and finish in any
order. A distinct request replacing a scan in the **same tab** cancels and
invalidates the previous ticket without touching other tabs. An ID may never
be reused in the same registry, even after completion. Capacity is limited
to 64 concurrent tabs and 4096 request IDs for the registry lifetime; further
requests fail closed without evicting or reusing active jobs.

The adapter must check isCurrent(ticket) after each asynchronous await and
before applying any result to a tab. The complete(ticket) method only retires
correlation: it cannot authorize opening, certify clean bytes, or resume
navigation. invalidateTab(tabId) invalidates one tab's ticket and invokes its
cancellation callback. Future tab-close/navigation tasks must independently
wire verified browser events and guarantee native-process cleanup.
dispose() first invalidates every ticket, then cancels all active callbacks.
Throwing and rejected async cancellation callbacks do not affect other tabs.

This work does not implement an enforceable interception point, request-byte
handoff, holding page, PDF identity verification, navigation restoration,
native scanner readiness or user opt-in. Those are separate prerequisites
in section 12.3. The prior pre-load gate assessment (opener-0782) is
nonblocking and explicitly does not authorize automatic interception.
Scanner file identity, ClamAV, signature freshness, quarantine, user
preferences and scan-before-open remain authoritative in native code.

The existing WebExtensions npm test suite, executed by CI, automatically
includes tests/pdf-tab-scan-registry.test.mjs. It covers cross-tab isolation,
out-of-order completion, same-tab replacement, stale/forged tickets, replay,
bounded capacity, hostile inputs, cancellation failure and unchanged scanner
and preference boundaries.
