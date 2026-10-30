# Existing-destination warning for Maximum safe copies — opener-0546

This independent, non-writing policy guard implements the overwrite-warning
half of §8.3 safe-copy management. The save UI or destination writer is a
separate task (opener-0544), not yet part of the installed Built-in handler.

Before offering a sanitized-copy destination, call
`review_sanitized_copy_destination(destination)` in
`maximum_overwrite_warning.py`. If its `requires_confirmation` flag is
true, display its fixed `warning` and present distinct **Replace** and
**Cancel** actions. Cancel is the default; the caller must not write anything
unless the user explicitly selects Replace. Before attempting the operation,
call `require_sanitized_copy_destination_confirmation(review,
confirmed=True)`; without that exact affirmative value, an existing file
cannot pass the review. A new destination does not require a warning.

The review tracks the existing file's identity, type, size and timestamps.
A new file appearing at a previously free path, changes to an existing file,
or a destination disappearing between review and approval requires a fresh
user review. Symlinks (including dangling links), hardlinked files,
directories and other nonregular targets are refused even with confirmation.
Messages do not interpolate document content, paths or filenames.

**Critical integration constraint:** The guard itself does not save or grant
opening permission. The save implementation must enforce exclusive creation
for a previously absent destination, and perform an identity-checked, atomic
replacement after confirmed review for an existing destination, to close any
race between review and the actual filesystem operation. It must never
silently fall back to a destructive write if an operation fails. Preserve the
original source, the generated-copy scan gate, quarantine and user preferences.

The existing Maximum profile is not enabled by this work. The dedicated
portable CI test suite verifies affirmative consent, decline, modified or
replaced destinations, symlink/hardlink/directory refusal and safe diagnostics.
