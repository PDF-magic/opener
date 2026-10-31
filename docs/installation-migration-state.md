# Durable installation migration state (opener-0949)

The legacy installer records its current attempt in the private installation
directory as .installation-migration.json. The status command
(python3 scripts/migration_state.py status) reports not_started, partial, or
complete without creating files or changing installed settings.

The journal begins before installer mutations and records completion only
after app registration, update-agent migration, Finder workflow handling, and
PDF-handler status succeed. An interrupted attempt reports partial; rerunning
starts a fresh attempt and revalidates existing installer safety guards. Older
attempts cannot mark a newer run complete. Repeating completion is harmless.

The previous success time is retained across interrupted reinstalls. Journal
and lock files are bounded, private regular files written without following
symlinks. Unsafe or malformed state aborts instead of being overwritten.
This state is not a scanner success stamp, signature freshness approval,
rollback mechanism, or permission to open a PDF; the existing scan gate,
user preferences, and Finder backups remain authoritative.
