# Native host uninstall registration cleanup (opener-0651)

`unregister-hosts.py` is the **explicit, per-user native host registration removal
step for uninstalling the current opt-in Chromium-family and Firefox registrations**.
Run it **before or after** removing the native host executable, supplying the
exact original absolute executable path and approved extension identity.
The executable need not still exist. No standalone application uninstaller
exists yet, so nothing silently deletes registrations just because an app is
removed; invoke this command in the uninstall workflow.

On macOS, to remove Chrome and Firefox registrations:

```sh
python3 native-messaging/unregister-hosts.py \
  --host-path "$HOME/Library/Application Support/Studio/allow-and-open/pdf-magic-native-host" \
  --browser chrome --extension-id ACTUAL_ORIGINALLY_APPROVED_EXTENSION_ID \
  --browser firefox --development
```

For Firefox on Linux, omit the Chrome arguments:

```sh
python3 native-messaging/unregister-hosts.py \
  --host-path /absolute/original/path/to/native-host \
  --browser firefox --development
```

Only the precise per-user Chromium-family macOS, Firefox macOS, and
Firefox Linux `org.pdfmagic.opener.json` files created by the reviewed
installers are eligible. Each manifest must **byte-for-byte match** the installer's
canonical schema, original absolute executable path, and exact approved
extension allowlist. The Firefox development-only ID requires an explicit
`--development` flag. Chromium-family origin order must match the original Chrome installation.

Cleanup never creates directories, runs or deletes a host executable,
removes user preferences, changes a browser extension's permissions, or
modifies scanner policy, signatures, file integrity, quarantine, or PDF
opening decisions. Missing manifests are a harmless no-op. Unrecognized,
modified, or symlinked manifests and directory links are refused; all
selected existing targets are checked before any removal. Other browser
manifests and files in the directories are preserved, as are the directories
themselves. The cleanup is safe to invoke again.

The reviewed opener-0643 Chromium registrar (PR #421) also writes to
`chromium`, `chrome-for-testing`, `brave`, `edge`, `vivaldi` and `arc`
on macOS. Select each registration that you actually installed, for example:

```sh
python3 native-messaging/unregister-hosts.py \\
  --host-path "$HOME/Library/Application Support/Studio/allow-and-open/pdf-magic-native-host" \\
  --browser chrome --browser chromium --browser brave --browser edge \\
  --extension-id ACTUAL_ORIGINALLY_APPROVED_EXTENSION_ID
```

Use the **same approved extension ID(s), in original order**, that were
recorded in Chrome's source registration copied to the other browsers.
`--browser opera` refers to the **same physical file as Chrome**;
selecting both aliases removes it only once. All selected targets are
preflighted before any deletion; a modified target prevents removal of
every selected registration. Browser profiles, other host names, and
unselected native registrations remain intact.

This cleanup does **not** guess or remove Windows registry keys, machine-wide
hosts or Safari containing-application data. Safari native messaging is
embedded in its containing app, not a standalone host-manifest registration.

Run `python3 test-native-host-uninstall.py -v` for disposable macOS/Linux
registration fixtures. This test is run in the existing `scanner-tests` CI
job; it never modifies a real browser profile or uses an installed scanner.
