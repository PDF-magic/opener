# Safari Web Extension build target (opener-0567)

`PDFMagicOpenerSafari` is a **separate macOS Safari Web Extension target**
inside `PDFMagicOpener.xcodeproj`, embedded in the existing
`PDFMagicOpener.app` at `Contents/PlugIns/PDFMagicOpenerSafari.appex`.
Xcode copies the **same** shared `extensions/webextension/manifest.json`
to `Contents/Resources/manifest.json` inside the .appex.

This adds a target and build packaging, **not** an active PDF integration.
The shared Manifest V3 contains no permissions, host access, actions, content
scripts or background worker. The Swift request handler accepts only a bounded, versioned `native.status`
request and returns `status: inactive` with both `scanVerified` and
`authorizesOpen` false. All other requests return no items. It cannot scan,
sanitize, launch, or approve PDFs, or message the parent app.
Embedding does not automatically enable the extension in Safari. An installed
host app may make the extension visible in Safari's extension preferences;
the user controls enabling it.

The Safari extension has only the sandbox entitlement, with no file, network,
application group, or native messaging privileges. The host application's
default PDF handler registration, ClamAV scan gate, signature freshness,
quarantine, verified file handoff, and user preferences are unchanged.
Future Safari functionality requires separately reviewed implementation.

Run `python3 test-safari-extension-target.py -v` for portable structural
tests. macOS CI builds the app and checks the actual embedded .appex,
executable, Info.plist and byte-for-byte shared manifest without launching
Safari or installing an extension.

## Inert shared background entry (opener-0568)

The shared Manifest V3 now declares a **no-op module service worker**. The
Safari extension resources bundle `background.js` directly beside the exact
shared `manifest.json`; neither file is generated from document contents.
The fixed script registers no listeners or messaging, reads no PDFs, and has
no browser privileges or native scanner access. Its bundle presence and exact
source bytes are verified by the Safari CI checks. This scaffolding does not
make the extension functional or grant a PDF opening verdict.

## Inactive toolbar popup (opener-0576)

The toolbar opens a local, read-only **Not active** panel supplied by the
shared `src/popup.html` and `src/popup.css`. Safari's app-extension Resources
bundle packages both files beside the shared manifest. Xcode and portable
CI check the exact source bytes; no scripts, browser APIs, remote resources,
scanner commands or native messaging are permitted. This popup does not
activate the browser integration or change the user's selected PDF handler.

## Open native preferences (opener-0577)

The static shared popup now includes a single opt-in
**Open PDF Magic Preferences** link. It requests the registered local macOS
preferences URL, which may trigger a browser confirmation. The source and
bundled Safari popup are byte-identical and retain their explicit inactive
PDF scanning status. This is not an extension-to-scanner message or PDF
opening capability; the native handler cannot invoke the scanner or approve a PDF.

## Exclude private windows by default (opener-0593)

The embedded shared Manifest V3 now declares `"incognito": "not_allowed"`.
Native CI verifies the exact manifest bytes inside the built Safari .appex.
Safari also provides its own user-managed private-browsing access setting;
the manifest flag alone is not a claim that Safari will block every
user-authorized private window on every release. The extension remains inert,
without page access, native messaging or PDF opening. Future activated Safari
integrations must separately review and test private-context exclusion.

## Safari permission regression coverage (opener-0612)

The Safari-specific permission tests exercise the **current inert extension**
without installing it or claiming that Safari has approved access.
`test-safari-extension-permissions.py` checks the source and built .appex
manifests, the sandbox-only entitlement, and regressions that would introduce
required browser permissions, website access, optional native messaging, or
private-browsing eligibility. The build-time check compares the embedded
manifest byte-for-byte with the reviewed shared source.

`extensions/webextension/tests/safari-permission-handling.test.mjs` uses
injected Safari-like WebExtensions permission APIs to test opt-in-only
`downloads` requests, explicit denials, rejected or unavailable APIs,
revocation and non-restoration, and rejection of undeclared website/native
permissions. A positive download grant is **not** a PDF scan verdict or
authorization to open a document. The real extension background remains inert; the native handler replies
only to safe status requests. These tests do not request Safari privileges,
activate monitoring, read browser history, or change native user preferences.

Run `python3 test-safari-extension-permissions.py -v` and
`cd extensions/webextension && npm run build && npm test` locally.
The existing portable scanner CI job runs both suites; macOS CI additionally
checks `--verify-built-app` against the Xcode-produced embedded extension.
Safari Settings authorization prompts and live browser behavior require a
separate interactive Safari test after activation/native messaging integration
is implemented; no headless unit test can certify a real user's Safari grants.

## Native message adapter (opener-0610)

The native `SafariWebExtensionHandler` now reads Safari's
`SFExtensionMessageKey` from the first `NSExtensionItem`, validates a
single version-1 shared envelope (`request`, `native.status`, ASCII
`requestId`, null payload, no extra fields, at most 16 KiB), and returns a
matching envelope inside a new `NSExtensionItem`. The only possible payload
reports `{status: "inactive", scanVerified: false, authorizesOpen: false}`.
Invalid or unsupported requests get no response items; no error details,
file paths, URL, profile data, or input payload are forwarded.

This is a **dormant, read-only adapter**, not a browser-to-scanner bridge:
the shared manifest intentionally does not declare Safari's required
`nativeMessaging` permission; the background script registers no
listeners or senders. Enabling native messages and authenticating privileged
actions are separate, reviewed tasks. No file, app group, network or scanner
privilege was added, and user preferences and all native scan gates are intact.

Run `swiftc -parse-as-library -warnings-as-errors
extensions/safari/SafariWebExtensionHandler.swift
test-safari-native-messaging.swift -o /tmp/test-safari-native-messaging`
and execute that temporary binary for functional request/rejection coverage.
The macOS CI job runs this test and builds the real Safari .appex.
