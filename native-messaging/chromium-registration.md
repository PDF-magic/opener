# Register the native host for Chromium-family browsers (opener-0643)

This opt-in macOS command extends the **existing Chrome registration from
opener-0639** to all other supported Chromium-family browser host locations.
First follow [the approved Chrome registration procedure](chrome-registration.md),
using the actual installed extension ID(s) and an already-built native host.
Do not guess extension IDs. Once the Chrome host manifest exists, run:

    python3 native-messaging/register-chromium-hosts.py

The command validates the Chrome registration's canonical
`org.pdfmagic.opener` identifier, stdio transport, absolute executable path,
and distinct exact `chrome-extension://` origins (no wildcards). Missing or
unapproved Chrome registration fails before writing anything. It **does not
create another Chrome manifest or decide the approved extension ID**.

Google Chrome and Opera share Chrome's documented macOS native-host location.
The tool publishes the exact existing Chrome manifest to Chromium, Brave,
Microsoft Edge, Vivaldi and Arc user-specific NativeMessagingHosts folders:
seven supported browsers, six distinct registration locations, and **five**
additional files. No Firefox or Safari registration is touched.

There is no automatic installation, `sudo`, system-wide write, extension
permission grant, scanner access, or change to saved PDF user preferences.
Identical destination files remain untouched; differing registrations and
symlinked paths fail closed rather than overwriting user customizations.
The native extension remains inactive pending separately reviewed integration,
authentication, and scanner safeguards. A host manifest is not a scan verdict.

Run isolated, portable tests:

    python3 test-native-chromium-registration.py -v

References: https://developer.chrome.com/docs/extensions/develop/concepts/native-messaging
and https://learn.microsoft.com/en-us/microsoft-edge/extensions/developer-guide/native-messaging
and https://help.opera.com/en/extensions/message-passing/
and https://github.com/keepassxreboot/keepassxc-browser/wiki/Troubleshooting-guide
