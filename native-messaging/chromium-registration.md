# Register the native host for Chromium-family browsers (opener-0643)

This opt-in macOS command extends the **existing Chrome registration from
opener-0639** to other supported Chromium-family browser host locations.
First follow [the approved Chrome registration procedure](chrome-registration.md),
using actual installed extension ID(s) and an already-built native host.
Do not guess extension IDs. Once the Chrome host manifest exists, run:

    python3 native-messaging/register-chromium-hosts.py

The command validates Chrome's registered `org.pdfmagic.opener` manifest,
stdio transport, absolute executable path and exact, distinct
`chrome-extension://` `allowed_origins` (never wildcards). Without a
verified Chrome registration, it fails before any other browser is modified.
It **does not create a competing Chrome manifest or approve extension IDs**.

## Registration locations

The following eight targets match the canonical
[Chromium host inventory](chromium-registration-targets.json). All paths are
per-user macOS locations; the manifest filename is `org.pdfmagic.opener.json`.

- Google Chrome: `~/Library/Application Support/Google/Chrome/NativeMessagingHosts`
- Chromium: `~/Library/Application Support/Chromium/NativeMessagingHosts`
- Google Chrome for Testing: `~/Library/Application Support/Google/ChromeForTesting/NativeMessagingHosts`
- Microsoft Edge: `~/Library/Application Support/Microsoft Edge/NativeMessagingHosts`
- Brave: `~/Library/Application Support/BraveSoftware/Brave-Browser/NativeMessagingHosts`
- Vivaldi: `~/Library/Application Support/Vivaldi/NativeMessagingHosts`
- Arc: `~/Library/Application Support/Arc/User Data/NativeMessagingHosts`
- Opera: `~/Library/Application Support/Google/Chrome/NativeMessagingHosts`

Opera uses Chrome's publisher-documented native host lookup directory.
Chrome for Testing has its own directory on Chrome 146 and later. The command
retains Chrome/Opera's already-approved file, then installs exact copies to
the other **six** unique browser directories. Browser versions, profiles or
policies with different lookup behavior require separate verification.

**By default, no browser native messaging host is registered or enabled by this project.** Registration is not automatic and
does not grant the browser extension `nativeMessaging` permission. The native
host still cannot perform or authorize scans. ClamAV signature freshness,
file integrity, quarantine and verified opening remain independent required
gates, and the user's selected PDF destination remains unchanged.

No `sudo`, system-wide write, Firefox or Safari registration is used.
An identical destination is a no-op; any conflicting existing manifest or
symlinked path is rejected before writes, preserving user customizations.

Run the portable, isolated regression tests:

    python3 test-native-chromium-registration.py -v

Source references:
- https://developer.chrome.com/docs/extensions/develop/concepts/native-messaging
- https://learn.microsoft.com/en-us/microsoft-edge/extensions/developer-guide/native-messaging
- https://help.opera.com/en/extensions/message-passing/
- https://github.com/keepassxreboot/keepassxc-browser/wiki/Troubleshooting-guide
