# Firefox native messaging host registration (opener-0644)

`host-manifest.template.json` defines the **Firefox** native messaging host
`org.pdfmagic.opener` with `type: "stdio"` and a deliberately narrow
`allowed_extensions` allowlist. The only currently declared Firefox Gecko add-on
ID is `pdf-magic-opener@example.invalid`, a **development placeholder**, not a
production publisher identity. The registrar checks the canonical
`../host-identity.json` and `../../extensions/webextension/firefox/gecko.json`
before writing a manifest, so an identity change fails closed until the allowlist
and registration are deliberately reviewed together. Do not add wildcards or
unreviewed extension IDs.

The JSON template is **not an installed browser manifest**: its `path` token
must be replaced with the absolute path to a compiled, executable native host.
Build the transport-only host with the existing `Host.swift` and
`HostStatus.swift` sources as described in `../host-executable.md`, then opt in
explicitly from the repository root (Node.js 20+):

```sh
node native-messaging/firefox/register.mjs --host /absolute/path/to/pdf-magic-native-host --development
```

The registrar writes `org.pdfmagic.opener.json` only into the current user's
Firefox native messaging host directory:

- macOS: `~/Library/Application Support/Mozilla/NativeMessagingHosts/`
- Linux: `~/.mozilla/native-messaging-hosts/`

It does **not** register a Chromium host, install an executable, modify Firefox
profiles, enable extension permissions, use a system-wide registration directory,
or launch a scanner. Windows Firefox registration uses a different registry-based
mechanism and is deliberately unsupported by this macOS-focused installer.
Existing manifests are preserved unless byte-for-byte identical; the operation
is idempotent, owner-only, and fails instead of overwriting custom registration.
To migrate an existing registration, inspect and manage it manually rather than
silently replacing it. No manifest is written simply by building or testing.

**Not a working browser integration.** The current unsigned Firefox package has
no `nativeMessaging` permission and no active native connection. Registration
alone does not authenticate a caller or authorize scanning, sanitizing, or opening
PDFs. The native host still responds `scanAvailable: false`. A publisher-owned,
Mozilla-signed add-on ID, a corresponding reviewed host allowlist, verified local
installation, explicit permission and authenticated scanner coordination are
separate future tasks. Existing scanner freshness checks, fail-closed behavior,
quarantine, and user PDF preferences are unaffected.

`extensions/webextension/tests/firefox-native-host-registration.test.mjs` runs
under the existing required `npm test` CI suite; its temporary registration
fixtures never touch a real user's Firefox configuration.
