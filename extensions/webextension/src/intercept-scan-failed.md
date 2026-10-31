# Display a blocking page when scanning fails (opener-0789)

The local `intercept-scan-failed.html` and CSS provide an extension-owned,
failure-only destination for a **future verified and opted-in interception
coordinator**. A caller that has actually held a PDF navigation and verified
a failed native scan may navigate **that held tab** to this extension page.
Loading this page neither intercepts traffic nor claims a scan occurred.

The page states **PDF blocked: scan did not complete**. It makes no malware
verdict or clean-scan claim. There is no Continue/Open/Retry button, external
link, automatic redirect, PDF URL, file path, dynamic error text, script, or
fallback browser/native opener. It instructs the user to close the tab and
perform a separate trusted local scan. It honestly limits protection to
requests that the coordinator really held; browser viewers, Finder, downloads
and other applications are outside this page's control.

Both Chromium and Firefox build and ZIP packaging validate and copy the
same assets using an explicit local allowlist, with no additional browser
permissions or changes to native signatures, quarantine, user PDF preferences
or selected opening applications. CI rejects active content, bypass controls,
false-success text and remote loads.

**Live display requires separate prerequisites:** opt-in automatic
interception with a proven browser-specific request veto, holding screen,
complete-PDF-byte transfer, authenticated scan response correlation, and
tab replacement on failure. None exists in the current inert background.
The page must never substitute for those checks. Timeouts, disconnects,
cancelled scans and incomplete or changed PDFs must never resume the held
PDF or be interpreted as clean by that future coordinator.

Run `npm run build`, `node scripts/build-firefox.mjs` and
`node --test tests/intercept-scan-failed-page.test.mjs` from
`extensions/webextension` or use the existing scanner-tests CI job.
