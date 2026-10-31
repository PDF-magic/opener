# Restore browsing after a successful intercepted scan (opener-0788)

This is a **dormant, fail-closed handoff contract**, not a deployed automatic
interceptor. The shared extension still has no interception grants or active
background listeners. No native coordinator can presently establish a held
request, authenticate a completed scan, or release browsing. The existing
browser/native safety boundary remains unchanged.

`createPostScanBrowsingRestoration` in
[`post-scan-browsing-restoration.js`](post-scan-browsing-restoration.js)
accepts only opaque scan/hold IDs and a numeric tab ID. An independently
authenticated coordinator must establish all of the following from its own
trusted session, **not** page content, browser metadata, or a "clean" label:

- The current active hold, tab and document identity and effective permission
- A complete, clean native scan of the exact PDF, with native session identity
- Continued ownership of the held request and revalidation at the actual
  browsing handoff
- A browser-supported restoration method that does not re-fetch or replay
  expiring/signed/private PDF URLs

Two methods are defined: **original-page** reveals an unchanged, already
preserved HTML tab without navigating again; **buffered-pdf-response** is
conditional on a separately implemented Firefox response-filter hold,
unchanged verified buffered bytes, permission grants and explicit approval
from native release policy (including the user's configured opening policy).
There is no equivalent verified buffering implementation for Chromium or
Safari, and ordinary Chromium MV3 request observation cannot suspend a
request waiting for a native scan.

The adapter reserves each hold before dispatch, rechecks the live coordinator
and document after acknowledgement, rejects failed/cancelled/incomplete/
malicious scans, changed tabs and revoked permissions, and suppresses replays.
An `accepted` acknowledgement means **restore requested**, not that browsing
was restored or that a PDF was authorized to open. The coordinator must
revalidate at the actual release boundary; the adapter cannot guarantee
that a browser or OS never opened the PDF independently.

**Prerequisite for live restoration:** separately implement and test the
opt-in, browser-specific blocking/holding integration, complete PDF-byte
handoff to the authenticated native scanner, live retention and permission
checks, and native-controlled release. Do not wire this module into
`background.js`, request new permissions, alter browser preferences or
weaken the scanner gate as part of this checklist item.

CI: `npm test` in `extensions/webextension` discovers
`tests/post-scan-browsing-restoration.test.mjs` automatically.
