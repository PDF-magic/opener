# Native messaging host identity (opener-0614)

The stable, cross-browser **native messaging host name** is
`org.pdfmagic.opener`. The canonical machine-readable definition is
[`host-identity.json`](host-identity.json). Future native messaging host
registration manifests and extension connection adapters must use that exact
name; do not derive it from a browser extension ID, application bundle ID,
installation directory, user preference or display name.

This lower-case, dot-separated identifier is valid for the Chromium and
Firefox native messaging host naming rules. It is **not** the Firefox add-on
ID (`pdf-magic-opener@example.invalid` is a reserved development ID),
a Safari extension bundle identifier, or an OS executable path. Changing the
native host name later is a compatibility-breaking protocol change and
requires an explicit migration and review rather than silent renaming.

**Not yet registered or enabled:** This file defines an identifier only. It
is not a native messaging manifest, installation instruction, executable,
authorization decision, host lookup or browser permission grant. No browser
extension currently connects to this host; no `nativeMessaging` permission
is added to the inactive WebExtensions manifests. A future separately
reviewed integration must register platform/browser-specific host manifests,
bind a trusted browser-extension identity through their allowed origin or
extension allowlists, verify local registration and authenticate the
connection. The name alone proves nothing about the host's authenticity.

Native scanner signature freshness, file integrity, quarantine, verified
opening and the user's configured PDF destination remain authoritative and
unchanged. The existing `extensions/webextension/tests/native-host-identity.test.mjs`
regression tests run automatically under the established `npm test` CI suite.
