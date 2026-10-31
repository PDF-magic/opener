# On-demand recent scan results (opener-0912)

The standalone preferences app now offers **Show recent scan results** on its
**Scan History** page. This destination remains hidden by default and can only
be shown when the owning integration independently verifies opt-in. No history
is read just by opening the gated page. Clicking the button retrieves **at most 20** existing
metadata-only entries from the optional private SQLite store, ordered by
timestamp (newest first) and insertion ID for ties. Only timestamp, canonical
final status, scanner version (or Unknown), and the actually enforced Built-in
profile are displayed. A clean scan is explicitly **not** evidence of a
successful file opening.

This viewer is read-only. It never creates a history database, enables
history collection, saves preferences, reads PDFs, launches files, or changes
scan blocking, quarantine, scanner settings, or operational scan caches.
Optional history remains **off by default**, and the native scan coordinator
does not yet collect history automatically. This change neither enables the
gated destination nor grants history collection consent. An absent store produces a clear
empty state; an unsafe, corrupt or unexpected schema produces an unavailable
state, not invented scan outcomes.

The reader validates a user-owned private directory (0700 or more restrictive),
a regular user-owned private database (0600 or more restrictive), refuses
symlinks and unexpected columns, and validates every displayed status,
timestamp, version and profile. It never reads document contents, filenames,
paths, URL histories or embedded attachments.

Portable source/CI guards and a macOS compiled Swift integration test use only
synthetic private SQLite data. Scanner behavior and explicit user customizations
are not modified.
