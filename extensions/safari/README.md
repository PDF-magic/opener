# Safari Web Extension build target (opener-0567)

`PDFMagicOpenerSafari` is a **separate macOS Safari Web Extension target**
inside `PDFMagicOpener.xcodeproj`, embedded in the existing
`PDFMagicOpener.app` at `Contents/PlugIns/PDFMagicOpenerSafari.appex`.
Xcode copies the **same** shared `extensions/webextension/manifest.json`
to `Contents/Resources/manifest.json` inside the .appex.

This adds a target and build packaging, **not** an active PDF integration.
The shared Manifest V3 contains no permissions, host access, actions, content
scripts or background worker. The Swift request handler returns no items;
it cannot scan, sanitize, launch, or approve PDFs, or message the parent app.
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
