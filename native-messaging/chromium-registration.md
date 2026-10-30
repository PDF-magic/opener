# Chromium-family native messaging registration inventory (opener-0642)

**Identification only — no browser native messaging host is registered or enabled.**
The canonical host name remains `org.pdfmagic.opener` from
[`host-identity.json`](host-identity.json). The machine-readable
[`chromium-registration-targets.json`](chromium-registration-targets.json)
records candidate *macOS per-user* lookup directories and the level of
evidence for each. These are not installer inputs or verified local installations.

## Browser-specific registration and lookup

| Browser | Registration handling | macOS per-user candidate `NativeMessagingHosts` directory |
| --- | --- | --- |
| Google Chrome | Its own documented location (baseline) | `~/Library/Application Support/Google/Chrome/NativeMessagingHosts` |
| Chromium | Separate from Google Chrome | `~/Library/Application Support/Chromium/NativeMessagingHosts` |
| Google Chrome for Testing | Separate beginning with Chrome 146; older releases shared Chrome locations | `~/Library/Application Support/Google/ChromeForTesting/NativeMessagingHosts` |
| Microsoft Edge | Distinct Edge location; do not assume Chrome's host is discoverable | `~/Library/Application Support/Microsoft Edge/NativeMessagingHosts` |
| Brave | Track Brave-specific registration; check current Brave lookup and Chrome fallback on an installed copy | `~/Library/Application Support/BraveSoftware/Brave-Browser/NativeMessagingHosts` |
| Vivaldi | Track Vivaldi-specific registration; verify its current native host lookup | `~/Library/Application Support/Vivaldi/NativeMessagingHosts` |
| Arc | Track Arc-specific registration; verify its current lookup and Chrome fallback | `~/Library/Application Support/Arc/User Data/NativeMessagingHosts` |
| Opera | Opera's published instructions currently specify the **Chrome directory**, not a distinct Opera directory; validate on Opera independently | `~/Library/Application Support/Google/Chrome/NativeMessagingHosts` |

**Evidence levels:** Chrome, Chromium, Chrome for Testing, Edge and Opera
locations are explicitly documented by their browser publishers. Brave,
Vivaldi and Arc directories appear in external native-messaging integrations;
they are *candidates requiring browser-specific verification*, not a promise
that a given version searches those paths. Chrome for Testing's separate
location begins with version 146. The lookup paths, fallback order, release
channels and extension IDs can change with browser releases.

- [Chrome / Chromium / Chrome for Testing native messaging](https://developer.chrome.com/docs/extensions/develop/concepts/native-messaging)
- [Microsoft Edge native messaging, including channel-specific directories and Windows fallback order](https://learn.microsoft.com/en-us/microsoft-edge/extensions/developer-guide/native-messaging)
- [Opera native messaging](https://help.opera.com/en/extensions/message-passing/)
- [KeePassXC Browser third-party host location troubleshooting](https://github.com/keepassxreboot/keepassxc-browser/wiki/Troubleshooting-guide)
- [Bitwarden desktop third-party browser host registration](https://github.com/bitwarden/clients/blob/main/apps/desktop/src/main/native-messaging.main.ts)

## Future registration prerequisites (not implemented here)

1. Before attempting installation, detect the **actual installed browser and
   channel** and validate that browser's *current* lookup mechanism. Never
   infer successful registration from a Chromium-compatible extension ZIP,
   a browser API namespace, or the existence of a Chrome directory. In
   particular, a Chrome fallback must be verified rather than assumed.
2. Use the same canonical host name but a reviewed browser-visible
   `org.pdfmagic.opener.json` at **each verified required location**.
   On macOS the executable `path` must be absolute; `type` must be
   `stdio`; `allowed_origins` must enumerate **exact, separately verified**
   `chrome-extension://<extension-id>/` identities (including distinct
   store IDs where applicable). Never use wildcards or derive allowlists from
   browser brand names. Do not install any host for a missing/unsupported
   browser or widen access to make a discovery test pass.
3. Treat browser registration and extension permission as separate gates.
   The current shared extension deliberately has no `nativeMessaging`
   permission and a disabled Scan PDF action; no browser-to-native scan
   coordinator is authenticated. Registry entries and user-level directories
   on Windows/Linux are also **out of scope** for this macOS inventory.
   Firefox and Safari have their own separate registration mechanisms.
4. Before enabling native actions, review browser origin authentication,
   host executable integrity, user consent, connection lifecycle and
   scanner dispatch. Native scanner ClamAV freshness, complete scans, file
   integrity, quarantine, verified PDF opening and all saved destination
   preferences remain mandatory; native messaging cannot bypass them.

The dedicated `chromium-native-registration.test.mjs` tests run in the
existing WebExtensions `npm test` / required `scanner-tests` CI job.
This inventory neither writes registration manifests nor changes any browser
profile, executable, scanner, permission, preference or CI workflow.
