# Application helper packaging (opener-0929)

The standalone macOS SwiftUI preferences app is **not** the installed PDF
scan gate. Build it with the existing `PDFMagicOpener` Xcode scheme first,
then stage a **separate** unsigned `PDFMagicOpener.app` containing the reviewed
native command-line helper executables:

```sh
python3 scripts/package_application_helpers.py \
  --app /path/to/DerivedData/Build/Products/Debug/PDFMagicOpener.app \
  --output-dir /path/to/unsigned-staging
python3 scripts/package_application_helpers.py \
  --verify /path/to/unsigned-staging/PDFMagicOpener.app
```

The helper binaries are compiled from the existing installer-reviewed Swift
sources (no fetched binaries or user-supplied shell commands), placed under
`Contents/Helpers/`, and checked for Mach-O signatures, executable bits,
an exact name allowlist and bundle identity. Included are the existing
scanner-approved launcher, browser/application discovery, PDF-handler status
and history helpers, target verification, and the **transport-only** native
messaging host. This is a staging operation: the input Xcode build and any
installed helper binaries or user preferences remain unchanged.

**Important security and lifecycle boundary:** The original PDF handler
`PDFOpener` and its `MakePDFMagicDefault` companion remain separately
installed by `install-allow-and-open.sh`, with their existing distinct
bundle identity. The staged preferences app does **not** register PDF
document types, install or activate browser native messaging, run scanners,
claim scan health, remove quarantine, or make itself a PDF opener. The
current installed helper paths are still authoritative; simply packaging a
copy does **not** migrate or activate them. Caller approval and all existing
security checks remain mandatory.

The result is an **unsigned development package**, not a notarized installer.
macOS CI checks both staging and verification after building the app and
keeps the existing Safari-only package independent and unchanged. Do not
ship the staging output as a trusted release without the separate signing,
notarization, and installer review.
