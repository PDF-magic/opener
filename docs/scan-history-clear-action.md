# Confirmed Clear History action (opener-0914)

In the optional **Scan History** preferences destination, **Clear History…**
opens an explicit destructive confirmation before deleting saved local scan
history. **Cancel** leaves all files untouched. The page remains hidden unless
the owning feature explicitly verifies history opt-in; this action does not
change the opt-in state or enable history collection.

The confirmed operation targets the private metadata database
`scan-history/scan-history.sqlite3` and only its SQLite `-wal`, `-shm`, and
`-journal` files. A private, owner-controlled directory, non-symlinked
regular files, strict permissions, and matching device/inode identities are
required. It unlinks these exact verified filenames through a pinned directory
descriptor, then synchronizes the directory. It never recursively deletes,
reads PDFs, modifies the operational scan cache or diagnostics, changes scanner
protections or preferences, or creates a missing history store.

Success updates the visible history state to empty; no saved history produces
a distinct informational result; an unsafe or failed deletion reports that
history could not be cleared safely. The history list is not used as a scan or
file-opening authorization. No existing scanner or browser settings are reset.

Portable CI guards and a compiled native macOS test verify confirmation,
actual deletion of synthetic SQLite metadata and sidecar files, absence and
repeat handling, rejection of symlink and nonprivate entries, and isolation of
other application files.
