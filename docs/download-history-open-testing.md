# Test opening files from browser download history (opener-0723)

This checklist item tests the **browser-owned Downloads/History open action**, not
PDF Magic Opener's optional "Open After Scanning" or "Download, Scan & Open"
actions. The browser's history/open UI is an **independent opening path**:
listening to `downloads.onChanged` or checking `downloads.search` does
**not intercept** a user's history click.
History clicks are not intercepted by PDF Magic Opener. The extension currently has an
inactive background and does not provide a universal pre-open scanner gate.

## Automated regression (CI)

Run `cd extensions/webextension && npm test`. The existing
`scanner-tests` CI job runs this suite automatically via
`node --test --test-concurrency=1 tests/*.test.mjs`, including
`tests/download-history-open.test.mjs`.

The deterministic, browser-neutral fake exercises: completed-history opening,
history clicks despite a download notification, a click while monitoring is
pending, browser danger labels, a denied optional downloads permission,
missing/incomplete items, untrusted browser metadata, and the separate native
scan-before-open boundary. It asserts that no history click is treated as a
verified native scan or a native-controlled opening command, that browser
URLs/paths are not included in assessment results, and that the inactive
manifest and user preferences remain unchanged.

The synthetic Node regressions alone do not drive a real browser download
page or establish browser-wide opening enforcement. **Section 16.4 now adds
a separate live Chromium browser regression (opener-1069)** in the existing
[Chromium CI workflow](../.github/workflows/chromium-webextension.yml).
It downloads an innocuous, locally generated PDF from loopback, verifies
the complete bytes, closes the source tab, finds the persisted entry in
`chrome://downloads/`, and performs a trusted click on the history
**Open** link. It requires Chromium to mark the entry as opened without
re-fetching the document. The run uses a disposable profile and makes no
PDF Magic scan, native handoff, or safety claim.

The live test verifies browser-owned opening in the tested Chromium version,
not every OS-associated external opener, Chrome/Firefox/Safari history UI,
or interception by PDF Magic. It does not certify a clean scanner verdict.

## Manual installed-browser acceptance procedure

Use a disposable non-private browser profile and an innocuous local test PDF.
Record the browser's exact name/version, operating system, extension build,
native host version, actual permission grants and selected application.
Leave the user's normal profile and custom PDF/download preferences alone.

1. Download a benign PDF, ensure it appears in **download history** (not
   only the transient download shelf), then use **Open** or click that entry.
   Record whether it opens in an inline tab, the OS-associated application,
   or the user's selected application, and whether the browser shows a warning.
2. Repeat the click while PDF Magic's download monitoring is **pending**,
   after the transfer is complete but before any authenticated scan result.
   Record actual timing and whether the browser allows opening. Do not
   report this as an intercepted or scanner-authorized open.
3. Repeat after a scan has failed, is unavailable or was cancelled, and when
   an item is missing, moved or erased. Use *synthetic test verdicts* for
   negative cases; do not open real malicious or untrusted content. Confirm
   the managed native workflow does not issue an open without a freshly
   verified clean result. The independent browser-owned path might still
   open and is **not blocked** by the extension.
4. Deny or revoke optional downloads permission and retry. Check that
   the extension does not request a new permission, change auto-open or
   default-app settings, dismiss native browser warnings or claim safety.
5. Exercise the distinct, explicit managed action only if a separately
   authenticated native coordinator is actually installed. Confirm ClamAV
   signature freshness, file identity/integrity, quarantine, and the
   user's **selected application** are rechecked by the native handler.
   Current transport-only native host cannot fulfill this prerequisite.

Run and record the above on Chrome/Chromium, Brave, Edge, Vivaldi, Opera, Arc,
Firefox, and Safari **where installed and supported**; mark unsupported or
unavailable actions as such rather than claiming success. The history-click
test on an actual browser and end-to-end native handoff remain **manual,
not executed by this automated regression**. Browser-specific permission
semantics and Safari opening APIs require direct verification.

Expected result today: a browser may open a PDF from download history
independently of PDF Magic Opener. That is an observed bypass risk, not a
reason to weaken mandatory scanner checks for PDF Magic's own workflow.
See [controlled browser opening](download-opening-browser-support.md) and
[opening-before-monitoring assessment](../extensions/webextension/src/download-early-open-assessment.md).
