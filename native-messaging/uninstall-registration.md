# Native host uninstall registration cleanup (opener-0651)

`unregister-hosts.py` is the **explicit, per-user native host registration removal
step for uninstalling the current opt-in Chrome and Firefox registrations**.
Run it **before or after** removing the native host executable, supplying the
exact original absolute executable path and approved extension identity.
The executable need not still exist. No standalone application uninstaller
exists yet, so nothing silently deletes registrations just because an app is
removed; invoke this command in the uninstall workflow.

On macOS, to remove both existing registrations:

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

Only the precise per-user Chrome macOS, Firefox macOS, and Firefox Linux
`org.pdfmagic.opener.json` files created by the reviewed installers are
eligible. Each manifest must **byte-for-byte match** the installer's
canonical schema, original absolute executable path, and exact approved
extension allowlist. The Firefox development-only ID requires an explicit
`--development` flag. Chrome origin order must match the original installation.

Cleanup never creates directories, runs or deletes a host executable,
removes user preferences, changes a browser extension's permissions, or
modifies scanner policy, signatures, file integrity, quarantine, or PDF
opening decisions. Missing manifests are a harmless no-op. Unrecognized,
modified, or symlinked manifests and directory links are refused; all
selected existing targets are checked before any removal. Other browser
manifests and files in the directories are preserved, as are the directories
themselves. The cleanup is safe to invoke again.

Other Chromium-family registrars are separately under development in
opener-0643 (PR #421). This cleanup does **not** guess or remove those
browser-specific locations, Windows registry keys, machine-wide hosts,
or Safari containing-application data. Add support only after those
registrations and their uninstall ownership rules are reviewed.

Run `python3 test-native-host-uninstall.py -v` for disposable macOS/Linux
registration fixtures. This test is run in the existing `scanner-tests` CI
job; it never modifies a real browser profile or uses an installed scanner.
