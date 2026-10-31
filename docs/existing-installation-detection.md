# Existing installation detection (opener-0933)

Run `python3 scripts/detect_existing_installations.py` to inventory known
macOS application bundles in `~/Applications` and `/Applications` without
changing them. The optional repeatable `--applications-dir` argument limits
search roots for tests or manual diagnosis. Results are JSON.

The recognized application IDs are `local.studio.brave-pdf-opener` (the
original scan-gated `Open PDFs in Brave.app` and renamed `PDF Magic Opener.app`)
and `local.studio.pdfmagicopener.swiftui` (the separate SwiftUI preferences
application, `PDFMagicOpener.app`). A bundle with either known identifier is
reported even if renamed. Known names with a missing, invalid, symlinked, or
foreign `Contents/Info.plist` are marked `unverified_candidate`, not trusted.
Unknown application bundles are omitted from the inventory.

**Read-only boundary:** Detection neither migrates applications nor changes
Launch Services associations, scanner configuration, selected browsers, or
user preferences. The output is diagnostic evidence, **not** permission to
rename, remove, overwrite, execute, or replace any installed bundle. Future
migration must independently revalidate bundle identity and resolve conflicts
before making changes. The Safari app-extension ID is not a standalone app.
