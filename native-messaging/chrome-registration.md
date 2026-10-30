# Chrome native host registration (opener-0639)

Google Chrome on macOS discovers a native messaging host through the per-user
manifest at:

    ~/Library/Application Support/Google/Chrome/NativeMessagingHosts/org.pdfmagic.opener.json

The opt-in installer `register-chrome-host.py` generates Chrome's exact JSON
manifest containing `name`, `description`, an **absolute** executable `path`,
`type: "stdio"` and `allowed_origins`. The host name is loaded from the
canonical `host-identity.json` and is never duplicated or changed.

## Registration (manual, only after identifying the extension)

First build the **existing** standalone host on macOS, in a stable location
controlled by the user, for example:

```sh
mkdir -p "$HOME/Library/Application Support/Studio/allow-and-open"
xcrun swiftc -O -parse-as-library -warnings-as-errors \
  native-messaging/Host.swift native-messaging/HostStatus.swift \
  -o "$HOME/Library/Application Support/Studio/allow-and-open/pdf-magic-native-host"
```

Find the **actual installed Chrome extension ID** in chrome://extensions
(enable Developer mode). An ID is 32 lower-case letters a–p. Do not use the
test-only example ID or an unverified ID from another extension. Explicitly
approve only that installed extension's identity and register it:

```sh
python3 native-messaging/register-chrome-host.py \
  --host-path "$HOME/Library/Application Support/Studio/allow-and-open/pdf-magic-native-host" \
  --extension-id ACTUAL_APPROVED_32_CHARACTER_EXTENSION_ID
```

Replace the uppercase placeholder with the real lowercase ID before running.
Repeat `--extension-id` only for other independently approved extension IDs.
Each becomes one exact `chrome-extension://<id>/` origin; wildcards, URLs,
malformed IDs and an empty allowlist are refused. The installer never guesses
an ID from unpacked builds, Chrome for Testing, a developer profile, or
the extension's name. The manifest file is created atomically with mode 0600.
An identical registration is a no-op. A different existing registration,
including a symlink, is **not overwritten**; review it manually instead.
Other browser host manifests and preferences are never modified.

Only Google Chrome's per-user **macOS** registration directory is supported
here; Brave, Arc, Chromium, Firefox, Windows and Linux registration remain
separate integration tasks. This script neither compiles nor installs
a scanner, nor registers a host automatically as part of the PDF opener installer.

**Trust boundary:** Chrome's `allowed_origins` restricts which *extension IDs*
can connect through Chrome; it does not authenticate the executing process,
establish user intent, or grant permission to scan. The shared WebExtensions
manifest still does not declare `nativeMessaging`, and the popup remains
inactive. The native host responds with transport-only/unavailable states;
actual scanner coordination must separately enforce authenticated caller
identity, explicit user file selection, ClamAV freshness, full scan/integrity
checks, quarantine and verified opening, without modifying user preferences.

Run `python3 test-chrome-native-host-registration.py -v` to test the
manifest schema, exact origins, path validation, private macOS registration,
idempotence, conflict refusal, and symlink safety without touching real
Chrome profiles.
