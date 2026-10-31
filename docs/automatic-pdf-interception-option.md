# Optional automatic PDF interception setting (opener-0783)

The macOS **Browsers** preferences page includes an **Enable Automatic PDF
Interception** per-browser opt-in only when an eligible browser is actually
discovered as an installed, executable app.

Today the only *documented candidate API* browser IDs offered in the setting
are Google Chrome, Microsoft Edge and Mozilla Firefox. Chrome and Edge have
documented Manifest V3 declarative network rules; those **cannot pause an
arbitrary PDF response for a native ClamAV scan**. Firefox's response stream
filter offers a possible future implementation, but no verified integrated
scan-before-render gate exists. The other Chromium-based browsers have
conditional, unverified deployment behavior; Safari's interception support is
version-specific and unverified. They are **not** shown as eligible opt-ins.

The persisted key \`automaticPDFInterceptionOptIns\` holds independent Boolean
choices by browser bundle identifier, defaults to no opt-ins, refuses unknown
IDs or malformed root data, and preserves all unrelated preferences.
Even if opted in, **automatic interception remains inactive in every browser**.
This is a recorded preference, never a network or native permission grant,
a scan verdict, or a file-open authorization. Enabling a working interception
integration later requires separate browser permission, installation/version
tests, a trusted scanner connection, complete-byte native verification,
timeouts, revocation handling, quarantine and safe application handoff.
A future integration must not interpret this preference alone as permission
to begin interception.

The browser extension manifests, inactive service worker, browser opening
preferences, default PDF handler, scanner protections and existing custom
application choices remain unchanged.

CI tests exercise per-browser filtering, absent/malformed defaults,
cross-launch persistence, independent browser choices, no-op unsupported IDs,
user preference preservation and inactive extension guarantees. This work
does not implement interception itself; see
[the enforceability assessment](../extensions/webextension/src/pdf-interception-point-assessment.md).
