# Chromium extension API change watch (opener-1164)

The read-only **Chromium extension API watch** GitHub Actions workflow checks
Google's official [Chrome Extensions "What's new"](https://developer.chrome.com/docs/extensions/whats-new)
announcements every Wednesday and on manual dispatch. It is separate from the
existing real Chromium/Chrome compatibility tests. The documentation includes
API additions, behavioral changes, Manifest V3/service worker behavior, and
browser packaging/extension policy announcements. All newly dated notices are
flagged for triage, including notices that turn out not to affect this project.

The script uses Python's standard library and fetches only the fixed official
HTTPS page, with a byte limit and a strict response-format check. It extracts
posted dates and headings, shows them in the GitHub step summary, and **fails**
the scheduled/manual job if any item is newer than the maintainer checkpoint
(`REVIEWED_THROUGH` in `scripts/chromium_extension_api_watch.py`). The initial
checkpoint is **2026-11-01**, after the existing notices published through
August 2026. Network errors, unexpected redirects, invalid responses, and
unparseable page formats fail instead of being treated as a clean review.
The PR/main CI contract job uses offline fixtures, not a fragile network check.

## Maintainer triage after an alert

1. Open the failed scheduled/manual workflow run and read each newly dated
   upstream notice; follow its official reference, migration, and deprecation
   links. Review **all** notices newer than the checkpoint, not only the first.
2. Compare affected Chromium extension APIs with the reviewed MV3 manifest and
   the actual APIs used by `extensions/webextension/src/` (especially runtime
   methods, optional `downloads`, action/popup, and service-worker behavior).
   Check Chrome, unbranded Chromium, Edge, Brave, Opera, Vivaldi and Arc where
   relevant. Browser feature availability is **not** proof of scan enforcement.
3. For applicable changes, open a separately scoped fix with browser-mock
   regressions and real Chromium/Chrome compatibility smoke tests; check other
   browser targets as necessary. Preserve explicit user consent, optional
   permissions, private-browsing exclusions, and fail-closed PDF handoffs.
4. In a reviewed PR, document the items assessed and compatibility evidence,
   then advance `REVIEWED_THROUGH` to the latest **actually reviewed** notice
   date. Re-run the manual watch and CI. Never advance it just to make CI green.

Run the offline regression without a browser or network access:

```sh
python3 tests/general/chromium-extension-api-watch.py -v
```

This watch is an **announcement review reminder**, not an exhaustive API diff,
a guarantee that undocumented upstream changes will be published here, or a
substitute for the already maintained real-browser tests. Later edits to old
announcements without a new posting date may not trigger the date checkpoint;
maintainers should also review the official API reference and release notes
when Chrome moves versions or an integration breaks. It never changes the
browser extension, grants privileges, activates interception, sends user data,
updates binaries, or reads PDF contents or application preferences.
