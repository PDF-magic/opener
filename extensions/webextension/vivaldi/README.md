# Vivaldi WebExtensions compatibility (opener-0602)

Vivaldi Stable is Chromium-based and consumes the same validated, inactive
Manifest V3 package as Chrome. A new Vivaldi-specific manifest, host
permission or native messaging grant is not necessary.

## Real-browser CI smoke test

The focused workflow .github/workflows/vivaldi-webextension.yml runs on
WebExtensions changes and via manual dispatch. It installs the **real Vivaldi
Stable browser** from Vivaldi's official HTTPS APT repository with a scoped
GPG signing key, then builds the shared Chromium Manifest V3 extension.

The dependency-free test driver launches the real /usr/bin/vivaldi-stable
process **headed in Xvfb** with an isolated temporary profile. It uses
Chromium's private CDP pipe and Extensions.loadUnpacked command to load the
reviewed unpacked dist/ assets, then verifies the extension inventory and
loaded popup document title through browser-level target metadata. Vivaldi
does not reliably support Chrome's renderer Runtime debugging protocol in
this CI environment, so the popup's disabled controls and CSS are
independently verified byte-for-byte against the validated build.
The special extension-debugging flag is CI-only and does not change the
product, allow private browsing or grant permissions. No substitute browser.
CI fails if Vivaldi cannot install or launch the reviewed extension,
report it enabled, or load the extension's local popup target.

The Vivaldi browser check verifies real extension installation and the
expected popup document title, and independently checks the source and
packaged manifest: required permissions and website hosts are empty,
optional downloads stays consent-gated, and private browsing is
disallowed. The validated static popup must show **Not active**, the
**Scan PDF** action must remain disabled with a visible accessible
explanation, and the local stylesheet and preferences link remain intact.
Effective permission-state inspection is not supported by this Vivaldi
test's browser-level protocol; no permission is requested.

The test never navigates to a public page, scans or opens a PDF, asks for
browser access, launches a native application, or touches a real user profile.
The temporary profile is deleted even if a test fails. ClamAV signature
freshness, file integrity, quarantine and user-selected safe PDF handoff
remain separate mandatory protections.

The checked-in Node.js tests also run in the existing required scanner-tests
job. The separate workflow provides actual Vivaldi integration verification
rather than treating manifest compatibility as a substitute for a browser test.

## Manual verification

Run npm run build in extensions/webextension. In current Vivaldi desktop,
open vivaldi://extensions, enable developer mode, choose Load unpacked and
select extensions/webextension/dist. Confirm the expected extension icon
and name, inactive popup, disabled Scan PDF control and no optional downloads
permission granted automatically. Do not enable private browsing or grant
new permissions to perform this test.

**Coverage limit:** Automated Vivaldi Stable verification runs on Linux.
macOS/Windows, store distribution, future browser-to-native scanner links
and real PDF handoff require separate end-to-end testing.

Primary references:
- https://help.vivaldi.com/desktop/install-update/obtaining-official-builds/
- https://help.vivaldi.com/es/escritorio/instalacion-actualizacion/configuracion-manual-de-los-repositorios-de-vivaldi/
- https://playwright.dev/docs/chrome-extensions
