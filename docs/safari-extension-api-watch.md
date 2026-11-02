# Safari extension API change watch (opener-1166)

PDF Magic Opener tracks Safari Web Extension API changes with a **read-only,
weekly** GitHub Actions watch (`.github/workflows/safari-api-watch.yml`).
The monitor reads the official [WebKit release feed](https://webkit.org/feed/)
for new Safari feature releases, Safari Technology Preview notes, WebExtensions
API changes, and native messaging updates. It also checks that the RSS window
still reaches the pinned **2026-11-01 UTC monitoring baseline**. That baseline
marks the start of automated tracking, **not** a claim that older releases have
been reviewed or that any new feature is compatible.

Run `python3 tests/general/safari-api-watch.py -v` for offline regression tests
and `python3 scripts/safari_api_watch.py` for the live check. The offline tests
run for pull requests, merge queues and `main`; public network polling happens
**only** on the weekly schedule or by manual `workflow_dispatch`. The live
check reports article links to the Actions step summary and fails when new
relevant articles need review, the feed is malformed/unavailable, or the feed
no longer covers the last review baseline. RSS detection is a triage signal:
Apple developer documentation can change without a WebKit blog post, and a
passing feed check is **not** evidence of runtime compatibility.

## Human review before advancing the baseline

1. Consult [Apple's Safari web extensions documentation](https://developer.apple.com/documentation/safariservices/safari-web-extensions), [Safari compatibility guidance](https://developer.apple.com/documentation/safariservices/assessing-your-safari-web-extension-s-browser-compatibility), and the upstream WebKit articles. Review every article newer than `WATCH_START` (including articles not matched by the automated keyword filter), plus Apple's Safari release notes and API documentation for changes omitted from RSS.
2. For the actual macOS target, compare the Safari-only MV3 manifest
   (`extensions/safari/manifest.json`), the app-bundled native messaging
   boundary (`extensions/safari/native-messaging.md`), optional `downloads`
   consent, private-browsing defaults, Swift handler, and available Safari
   runtime APIs. Do not assume Chromium, Firefox or Safari Technology Preview
   behavior automatically applies to stable Safari.
3. Run the existing Safari permission, native messaging, activation, embedded
   `.appex` and real Safari tests appropriate to the change. Confirm no new
   browser privilege, PDF-open approval, scanner bypass, private-window access,
   or preference migration occurs without a separate reviewed implementation.
   Record affected Safari/macOS/Xcode versions, links, test evidence and any
   follow-up issues/PRs; do not silently accept a breaking API change.
4. Only after investigating **all** articles in the window, advance
   `WATCH_START` in `scripts/safari_api_watch.py` to the UTC date of the latest
   fully reviewed article (never a future date), in a normal reviewed PR. This
   acknowledgement does **not** change the live extension, update software,
   enable permissions or mark automatic interception production-ready.

The RSS window is deliberately bounded and fail-closed: if it stops reaching
`WATCH_START`, the checker cannot prove it saw every intervening article and
requires a manual upstream backfill before the baseline can move. This is a
maintenance alert, not a reason to disable scanner protections. If the feed
is offline, rerun later; do not report a clean result. Follow Apple's official
API/release documentation separately because feed coverage is not exhaustive.
