# Firefox WebExtension API compatibility watch (opener-1165)

The **Firefox WebExtension API watch** checks the Mozilla/MDN browser compatibility
data (BCD) repository once a week and on manual dispatch. It records the last
reviewed upstream commit **per file** for the APIs and Manifest V3 keys used or
declared by the current Firefox scaffold. Changes signal **human review**; they
do not update browser extensions, change permissions or assert incompatibility.

## Tracked surfaces and upstream sources

- API: `action`, `downloads` (currently optional), and `permissions`.
- Manifest: `action`, `background`, `browser_specific_settings` (including Gecko
  metadata), `host_permissions`, `incognito`, `manifest_version`,
  `optional_permissions`, and `permissions`.
- Canonical data: [MDN browser-compat-data](https://github.com/mdn/browser-compat-data/tree/main/webextensions).
  Its file history is queried through the read-only GitHub commits API. The
  reviewed SHA for each path lives in `scripts/firefox_api_watch.py`, checked
  against the latest path-specific commit on November 1, 2026.
- During triage also consult [Mozilla's Add-ons engineering updates](https://blog.mozilla.org/addons/),
  [Firefox release notes](https://www.mozilla.org/firefox/releases/), and
  [Mozilla's browser compatibility guidance](https://extensionworkshop.com/documentation/develop/browser-compatibility/).

Changes to a BCD file may concern **Chrome, Safari, Firefox Android, or editorial
data only**. Conversely, BCD can lag a Firefox release. A passing watcher is
**not** a guarantee of compatibility or an audit of every browser behavior.
The pinned files are a targeted inventory, not a general Mozilla advisory feed.

## Alert review and safe follow-up

1. Open the failed scheduled or manually dispatched GitHub Actions run and
   note each changed or unavailable path and its reviewed/current SHA.
2. Compare the file history between those revisions. Determine whether the
   Firefox desktop `support.firefox`, deprecation, version, permission,
   manifest behavior, or implementation notes actually changed; consult
   Mozilla's latest WebExtension API announcements and release notes.
3. Check the configured Gecko minimum (`128.0`) and Firefox current/stable
   and applicable ESR behavior. Rebuild and test the Firefox manifest, ZIP,
   background isolation, popup, and permissions. Exercise a real Firefox
   build where a behavior change is suspected; do **not** infer compatibility
   from static BCD or mock tests alone.
4. File a narrowly scoped follow-up for any real incompatibility. Preserve
   the mandatory ClamAV scan-before-open gate, native messaging safeguards,
   no-extra-permissions policy, and existing user customizations.
5. Only after recording the source diff, Firefox impact and verification in
   that review, advance **affected** reviewed SHAs in a separate tested PR.
   Do not silently accept new upstream commits to make the alert green.

If upstream is unavailable, malformed, rate-limited, or a watched file was
removed, the job **fails** rather than reporting unchanged. Alerting occurs
through the failed Actions run; no extra credentials, issue-creation tokens,
or auto-update machinery are introduced. The workflow uses its ordinary
read-only `github.token` only on scheduled or manual checks.

## Checks

Offline contract tests (also run on PRs, merge queues, and `main`):

```sh
PYTHONPATH=. python3 tests/general/firefox-api-watch.py -v
```

Live upstream review (network, run only when explicitly investigating a change):

```sh
python3 scripts/firefox_api_watch.py
```

The upstream query is not performed during pull-request validation. This
watch does not access PDFs, scanner binaries, browser profiles, private
preferences or any secret-bearing files. The Firefox scaffold remains
intentionally inert; it cannot scan, sanitize or open a PDF.
