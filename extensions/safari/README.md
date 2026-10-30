# Safari Web Extension build target (opener-0567)

`PDFMagicOpenerSafari` is a **separate macOS Safari Web Extension target**
inside `PDFMagicOpener.xcodeproj`, embedded in the existing
`PDFMagicOpener.app` at `Contents/PlugIns/PDFMagicOpenerSafari.appex`.
Xcode copies the **same** shared `extensions/webextension/manifest.json`
to `Contents/Resources/manifest.json` inside the .appex.

This adds a target and build packaging, **not** an active PDF integration.
The shared Manifest V3 contains no permissions, host access, actions, content
scripts or background worker. The Swift request handler responds only to validated, inactive status requests;
it cannot scan, sanitize, launch, or approve PDFs, or message the parent app.
See [native messaging adapter](native-messaging.md) for the strict boundary.
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
opening capability; the existing native handler remains inert.

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
authorization to open a document. The real extension background and native
request handler remain inert; these tests do not request Safari privileges,
activate monitoring, read browser history, or change native user preferences.

Run `python3 test-safari-extension-permissions.py -v` and
`cd extensions/webextension && npm run build && npm test` locally.
The existing portable scanner CI job runs both suites; macOS CI additionally
checks `--verify-built-app` against the Xcode-produced embedded extension.
Safari Settings authorization prompts and live browser behavior require a
separate interactive Safari test after activation/native messaging integration
is implemented; no headless unit test can certify a real user's Safari grants.

## Unsigned Safari extension package (opener-0608)

The Xcode host application embeds the Safari Web Extension as a native
`.appex`. Unlike a Chromium or Firefox submission ZIP, a Safari Web
Extension is installed through a macOS host application. The CI macOS build
packages the verified `PDFMagicOpener.app` with its embedded extension as
`pdf-magic-opener-safari-<version>-unsigned.zip` and uploads it as a
short-lived GitHub Actions artifact.

This is an **unsigned development artifact**, not a signed, notarized,
installable production release or Mac App Store submission. Distribution
requires a separate signing and notarization workflow, an Apple developer
identity, and user-controlled installation and extension enabling. None of
those release credentials or operations are part of this task.

To package an existing unsigned Xcode Debug app from the repository root:

```sh
python3 scripts/package_safari_extension.py --app "/path/to/PDFMagicOpener.app" --output-dir "/path/to/artifacts"
python3 scripts/package_safari_extension.py --verify "/path/to/artifacts/pdf-magic-opener-safari-0.1.0-unsigned.zip"
```

The package builder rejects unknown files, symlinks, missing or nonexecutable
binaries, broadened browser privileges, mismatched source assets and unsafe
archive paths. CI validates the archive, extracts it without installation,
and rechecks the embedded Safari extension. No PDF scanning, native messaging,
Safari activation, native scanner changes, quarantine changes, or user
configuration changes are introduced.

## Safari activation acceptance test (opener-0611)

**Activation is controlled by the Safari user, not CI or the host app.**
Run the native build and bundled-extension verification in CI first.
On a disposable macOS Safari profile with the **installed, launched**
PDF Magic Opener host app, open **Safari > Settings > Extensions**.
Verify that **PDF Magic Opener Safari Extension** is listed. A development
build must be properly signed, or the tester must explicitly allow unsigned
extensions under Safari > Settings > Developer for that Safari session.
Never modify a user's existing Safari extension preferences for this test.

Compile the read-only probe on macOS:

```sh
xcrun swiftc -parse-as-library -warnings-as-errors test-safari-extension-activation.swift -o /tmp/TestSafariExtensionActivation
/tmp/TestSafariExtensionActivation --self-test
```

1. Leave the extension unchecked in Safari > Settings > Extensions and run
   `/tmp/TestSafariExtensionActivation --expect disabled`. This must exit
   successfully **only** when Safari reports the registered extension disabled.
2. Explicitly enable the extension in Safari's Extensions settings, then run
   `/tmp/TestSafariExtensionActivation --expect enabled`. Check the Safari
   toolbar popup: it must still say **Not active**, and explain that it
   **cannot scan, sanitize, or open PDF** files. Enabling the scaffold is not
   a malware-scan verdict or an authorization to open documents.
3. Uncheck the extension again and rerun
   `/tmp/TestSafariExtensionActivation --expect disabled`. The test must
   report disabled, with no change to existing PDF application preferences.
4. If the probe reports **not registered**, a SafariServices error, or a
   timeout, record an **inconclusive/failed test**, not a disabled or enabled
   result. Verify the installed host app, Safari profile and signing before
   retrying. The state query is designed for an extension embedded in its
   containing application; a standalone diagnostic process may not have
   the same registration context.

The probe only reads SafariServices activation state. It never enables
an extension, opens settings, changes permissions, scans PDFs, or modifies
ClamAV/quarantine checks. CI compiles the probe and exercises its state
decision matrix without installing the app or approving a Safari extension;
**actual end-to-end enable/disable is a manual macOS acceptance test**.
