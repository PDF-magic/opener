# macOS signing entitlements and hardened runtime (opener-1138)

This is a **configuration and verification** step for the macOS SwiftUI
preferences host and its embedded Safari Web Extension, **not** a distribution
authorization. It does not alter the separately installed `PDFOpener` scanner
gate, its executable helpers, signing identities, or existing user preferences.

- `PDFMagicOpenerApp/PDFMagicOpener.entitlements` is deliberately an empty
  dictionary. The host is **not sandboxed** and receives no special security,
  network, file, JIT, debugger, or library-validation exception entitlements.
  Its ordinary filesystem and process access is needed for its existing
  configuration and helper integration; adding sandboxing here without a
  separate migration and test would risk breaking installed functionality.
- `extensions/safari/SafariExtension.entitlements` retains precisely
  `com.apple.security.app-sandbox = true` and grants no additional rights.
  Browser-level optional permissions are governed separately by the Safari
  extension manifest and the user's consent.
- Both Xcode **Release** targets set `ENABLE_HARDENED_RUNTIME = YES`;
  Debug signing behavior remains unchanged. The embedded extension retains
  `CodeSignOnCopy`. Both Release targets explicitly disable Xcode's\n  injection of base entitlements, preventing ad-hoc signing from silently\n  adding the debugger's `com.apple.security.get-task-allow` right.\n  No broad hardened-runtime exceptions are introduced.

The distribution audit runs portable source checks and, on macOS, makes a
**temporary ad-hoc-signed Release build** with no developer certificates or
signing secrets. The macOS check uses `codesign --verify --strict`, checks the
CS_RUNTIME signature flag on **both** bundles, checks their bundle identities,
and compares their signed entitlements against the exact allowlists. It
rejects unsigned or unexpectedly privileged artifacts. To validate a separately
signed Release build without installing or launching it:

```sh
python3 scripts/verify_macos_app_signature.py --app /path/to/PDFMagicOpener.app
```

Ad-hoc signing verifies these build properties but **does not establish**
Developer ID trust, notarization, Gatekeeper acceptance, or a valid release.
The standalone native scan-handler and separately staged helper executables
are outside these Xcode targets and require their own audited signing,
hardened-runtime, packaging, and notarization handling before distribution.
Do not ship the unsigned/ad-hoc CI output or enable the guarded release path
on the basis of these checks alone.
