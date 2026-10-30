# Determine opening risk before download monitoring finishes (opener-0713)

The WebExtensions API exposes when the **browser transfer** completes,
but completion of the transfer is **not completion of PDF Magic Opener
monitoring or of an authenticated native ClamAV scan**. Users and other
applications may be able to open a downloaded file through a browser or
filesystem while post-download monitoring and scanning remain pending.

`assessDownloadOpeningBeforeMonitoringCompletes(downloadsApi,
permissionsApi, { kind: "monitoring-pending", id })` is an explicit,
passive, one-shot assessment for a trusted opted-in monitoring component.
It never registers event listeners until called, opens a file, blocks a
browser, or changes permissions or user settings. Only an exact-ID,
two-property monitoring-pending notice is accepted; the **trusted native
coordinator** must supply its own correct monitoring lifecycle, not page
content or a stale, browser-provided "scan complete" claim.

After checking the current optional `downloads` grant, the helper
uses only `downloads.search({ id })`. Permission removals or a changed,
recreated or erased matching download ID during an asynchronous lookup
invalidate the result. Ambiguous, missing, malformed, inaccessible, denied
or interrupted API data fails closed with a frozen generic status.

## Assessment output

All responses are fixed and frozen, and have
`openingBlocked:false`, `scanVerified:false` and
`authorizesOpen:false`.

- **`opening-possible`** with
  `browserMayOpenBeforeMonitoringCompletes:true`: the browser confirms
  the item has completed transfer, still exists, is not paused or resumable,
  and has no recorded download error. The browser/OS may let the user open
  the file before any separate monitoring or native scan finishes. This is
  a **possible bypass**, not proof that the file was opened, can definitely
  be opened in every browser, or has passed security checks.
- **`transfer-in-progress`** and **`transfer-interrupted`** with
  `browserMayOpenBeforeMonitoringCompletes:null`: native
  `downloads.open` ordinarily requires a completed item, but filesystem
  access or other browser actions cannot be ruled out. Neither status
  claims that opening is prevented.
- **`unknown`**, also with `null`: the API cannot establish a reliable
  transfer state or the optional permission was unavailable/revoked.
  Unknown never means safe or blocked.

No user file path, original URL, final URL, cookies, private referrer,
content bytes, browser danger label, or arbitrary diagnostics are returned,
logged, persisted, or sent to a host. A browser "safe" danger label is
not an antivirus verdict. No `downloads.open`, `pause`, `cancel`,
`removeFile`, download UI mutation or new permission is used.

## Security and integration limitations

This is a **capability/risk determination**, not an opening interlock.
Browser download-event observation does not grant an extension a universal,
synchronous veto over the browser's open UI, automatic-opening settings,
Finder or other filesystem processes. The current production extension
background/popup remains inactive, and the native messaging host is
transport-only. Therefore PDF Magic Opener cannot presently guarantee that
every third-party browser/OS opening waits for its scanner.

A future independently authenticated coordinator must revalidate
canonical file identity and bytes, run complete mandatory ClamAV scanning
with fresh signatures, retain quarantine, enforce the user's selected PDF
application and ensure **its own** opening commands only occur after all
gates succeed. Further browser-managed opening restrictions, if desired,
must be separately engineered and validated against actual supported
browser/OS behavior. Never mistake `opening-possible` for authorization.

The 14 tests in `tests/download-early-open-assessment.test.mjs` run
automatically in the existing WebExtensions `npm test` suite under
GitHub Actions `scanner-tests`. They exercise the transfer/monitoring
distinction, malformed and mismatched IDs, permission races, lifecycle
races, lack of claimed opening authorization, privacy and inactive setup.

API references:
- https://developer.chrome.com/docs/extensions/reference/api/downloads
- https://developer.mozilla.org/en-US/docs/Mozilla/Add-ons/WebExtensions/API/downloads/open
