# Opera WebExtensions compatibility (opener-0603)

Opera is Chromium-based but differs from Chrome in extension packaging,
the debugging protocol, permissions and popup behavior. The native macOS
Opera PDF-launch tests exercise opening previously scanned files in Opera,
not loading the shared WebExtension.

## Actual-browser CI test

The new scoped GitHub Actions workflow installs **real Opera Stable**
from Opera's officially signed Linux APT repository, using the publisher's
documented GPG signing-key fingerprint:
https://deb.opera.com/manual.html

The test builds the already validated, unpacked Chromium Manifest V3
extension from the shared project and uses a CI-only Puppeteer Core driver to connect to Opera's actual, locally
bound Chromium DevTools debugging endpoint in an Xvfb display with an
isolated, disposable profile. Opera is **not officially supported by
Playwright**; this test does not use Playwright's incompatible Opera launch
pipe or silently substitute Chromium. Missing or divergent Opera debugging
support is treated as a failure, not evidence of compatibility.

The browser smoke test checks that the real Opera instance loads the
extension background service worker and exposes the least-privilege
manifest: no required host or browser API permissions, private browsing
excluded, and optional downloads not silently granted. It checks Opera
renders the local popup, displays the inactive status, preserves the CSS
and native preferences link, and keeps Scan PDF disabled until a
verified native scanner is connected.

The test does not inspect web pages, fetch/download real PDFs, grant
browser permissions, contact native messaging, or launch applications.
Its profile is always removed. The workflow runs on extension and
workflow changes (or manual dispatch), not on unrelated macOS work.

## Manual compatibility check

Follow Opera's official unpacked extension procedure:
https://help.opera.com/en/extensions/testing/

After running npm run build inside extensions/webextension, open
opera:extensions, enable Developer Mode, select Load Unpacked Extension,
then choose extensions/webextension/dist. Verify that PDF Magic Opener
shows its Not active popup, Scan PDF is disabled, and optional downloads
access and private browsing are not enabled. Never grant extra
permissions to make a failing test pass.

This validates the inactive extension scaffold only; a live
browser-to-native scanner bridge, actual scanning and automatic PDF
opening remain independently gated, separately reviewed tasks. The
installed scanner's ClamAV freshness, integrity, quarantine, and
destination-app checks, along with all user preferences, are unchanged.
