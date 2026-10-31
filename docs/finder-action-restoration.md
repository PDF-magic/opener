# Restore the original Finder Quick Action (opener-0945)

The installer preserves the pre-migration Finder action as
`~/Library/Services/Allow and Open.workflow/Contents/document.wflow.before-brave`.
Migration does **not** replace an existing backup. This is separate from restoring
the macOS **default PDF handler**: the Finder Quick Action is a Services workflow,
not a system file association.

To inspect whether restoration is possible, from the project checkout run:

    python3 restore_finder_quick_action.py

To explicitly replace the managed Quick Action with the preserved original:

    python3 restore_finder_quick_action.py --restore

**Restoration is opt-in.** The original workflow may launch files without the
PDF Magic malware scan gate; restoring it is not equivalent to disabling or
uninstalling the system PDF handler. Do not use the original action for untrusted
files unless it independently scans them.

The restore operation reads the preserved backup, verifies both workflows are
regular files in a non-symlinked Services directory, and requires an unchanged
product-managed current action. If the current action has been customized since
migration, it **refuses** to replace it. It also refuses malformed/unsafe
backups. The original backup is retained byte-for-byte. When allowed, restoration
copies the exact saved workflow bytes through a staged same-directory file, with
existing permissions, rather than truncating the active workflow. A previously
removed active workflow can be recreated from the backup without overwriting a
concurrently created file. Running the command again is a no-op.

No Finder workflows, user scripts or PDF files are executed during inspection,
restoration or automated testing. Normal installation never calls this restore
operation. If macOS does not immediately refresh the Services menu after a
restore, reopen Finder; no automatic Finder restart is performed.
