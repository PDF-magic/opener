# Persistent configuration storage location (opener-0208)

PDF Magic Opener stores persistent configuration **locally in the current macOS
user's Library**. This is a storage-location decision, not a new configuration
schema or a migration. Existing values are authoritative.

| Configuration | Canonical location | Owner |
| --- | --- | --- |
| Shared UI preferences (scan progress and successful-scan notifications) | `UserDefaults(suiteName: "local.studio.pdf-magic-opener")`, backed by the user's `~/Library/Preferences/local.studio.pdf-magic-opener.plist` domain | SwiftUI preferences and installed PDF scan handler |
| Verified PDF application choice (`target-app.txt`), scanner tools, and signature database | `~/Library/Application Support/Studio/allow-and-open/` | Installed scanning helper and verified chooser |
| Existing previous PDF association (`previous-pdf-handler.txt`) | `~/Library/Application Support/Studio/allow-and-open/` | Installed PDF-handler history tool |

The macOS preferences system manages its own backing file, caching, and
synchronization: clients must use the shared `UserDefaults` suite, **not**
write its plist directly. Scanner-owned configuration continues to use the
existing Application Support directory. The standalone SwiftUI application
reads the installed target choice but cannot write `target-app.txt`
directly; verified application selection is delegated to the installed chooser.

Do not move the scanner's configuration into the UI preferences domain,
create parallel copies of existing settings, or place preferences inside app
bundles, temporary directories, cloud folders, or the repository. Future
versioned-schema and migration tasks can build on these locations, but this
task performs **no migration, initialization, reset, overwrite, or scanning
policy change**. Missing and unreadable settings retain the existing
fail-closed/default behaviors; installer reruns must preserve custom choices.
