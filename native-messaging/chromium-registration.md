# Register the native host for Chromium-family browsers (opener-0643)

Run the opt-in **macOS per-user** registration tool only after the Chrome-compatible
native-host manifest, approved extension origins, and installed executable exist
(opener-0639 and subsequent verified installation work). This task does **not**
create the manifest, choose extension IDs, enable native messaging permissions,
activate the browser extension, or install a native executable.

    python3 native-messaging/register-chromium-hosts.py --manifest /absolute/path/to/org.pdfmagic.opener.json

The manifest must name **org.pdfmagic.opener**, use stdio transport, point to
an existing absolute executable, and contain a nonempty list of distinct,
fully specified chrome-extension:// origins with no wildcards. Incomplete or
unapproved manifests fail closed before any registration is written.

Registration copies the exact approved manifest into the current user's
~/Library/Application Support/.../NativeMessagingHosts/org.pdfmagic.opener.json
for **Chrome, Chromium, Brave, Microsoft Edge, Vivaldi, and Arc**. **Opera**
uses Chrome's native messaging location on macOS, so registering Chrome also
covers Opera. This intentionally registers all seven supported Chromium-family
browsers, with six distinct locations; Firefox and Safari are out of scope.

The command does not run automatically, use sudo, modify system-wide browser
configuration, grant permissions, scan PDFs, alter browser preferences, or
change the user's saved PDF destination. An identical registration is left
untouched; an existing differing manifest or any symlinked registration path
causes a safe failure rather than overwriting the user's configuration.
The native host and browser connection still require separate end-to-end
review and authentication; host discovery alone authorizes no scanning.

Run isolated tests without registering anything on the host machine:

    python3 test-native-chromium-registration.py -v

Browser location references:
- Chrome / Chromium: https://developer.chrome.com/docs/extensions/develop/concepts/native-messaging
- Microsoft Edge: https://learn.microsoft.com/en-us/microsoft-edge/extensions/developer-guide/native-messaging
- Opera (Chrome directory): https://help.opera.com/en/extensions/message-passing/
- Brave / Vivaldi / Arc: https://github.com/keepassxreboot/keepassxc-browser/wiki/Troubleshooting-guide
