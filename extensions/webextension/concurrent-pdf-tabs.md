# Multiple concurrent PDF tabs — per-browser verification (opener-0808)

This test extends section 12.4 per-browser verification without implementing
or enabling optional automatic interception.

## Real Chrome verification

The existing pdf-tab-scan-registry.js module from opener-0792 already has
unit tests for bounded request IDs, tab isolation, cancellation and
out-of-order native results. This task does not replace or change that
registry.

The new test-chrome-concurrent-pdf-tabs.mjs script uses the existing
Chrome for Testing CI installation and a disposable browser profile.
It creates three different, valid one-page PDFs in memory with distinct
visible text, then serves them from an HTTP server bound only to 127.0.0.1.
The browser test:

1. Creates three independent real Chrome tab targets and DevTools sessions
   before any PDF navigation begins.
2. Navigates all three PDF tabs without waiting for a previous tab to
   complete. The server immediately sends PDF headers but holds all three
   response bodies until every request arrives. This proves overlap, rather
   than merely running three PDF navigations in sequence.
3. Keeps all three tabs open while foregrounding each in turn for
   inspection. Each tab must independently report its own original URL
   and an application/pdf document. Chrome's built-in viewer may be an
   out-of-process iframe target without a parent-tab link in DevTools,
   so the test separately requires at least three distinct built-in PDF
   viewer iframe targets in the otherwise empty disposable browser.
   One global viewer target cannot count three times.
4. Closes the second tab and re-verifies the other two PDF viewers remain
   active with their original URLs.
5. Tears down Chrome, DevTools, local server and temporary browser profile.

The fixtures contain no external resources, embedded JavaScript, launch
actions, user data or private files. The test does not change any installed
browser profile, default PDF application, extension permission, native
scanner setting or quarantine policy.

## Correlation regression tests

The new concurrent-pdf-tabs.test.mjs test exercises the already implemented
passive createPdfTabScanRegistry and createTabScanClosureGuard APIs together.
It covers three asynchronous results delivered out of order, closing a PDF
tab before a forged clean-looking result arrives, replacing the document
in one tab without impacting another, and disposing several pending scans
while invalidating tickets before cancellation callbacks.

These tests do not turn a ticket or an HTTP PDF response into a clean
scanner verdict or permission to open. The background extension remains
inactive. Real optional automatic interception requires separately
authenticated native scan correlation, effective pre-render response holds,
ClamAV scanning and freshness verification, quarantine and fail-closed
scanner-unavailability behavior. Those prerequisites are not implemented
by these tests.

## CI

The existing Chrome package smoke job runs the actual three-tab browser
script in a fresh CI browser. The scanner-tests job runs the portable
regression suite explicitly; the WebExtensions npm test wildcard includes
it too.

From extensions/webextension, run:

    node --test tests/concurrent-pdf-tabs.test.mjs
    node scripts/test-chrome-concurrent-pdf-tabs.mjs /path/to/chrome

The CI-only CHROME_TEST_NO_SANDBOX flag remains limited to the existing
isolated Linux test browser; no user or production browser flags change.
