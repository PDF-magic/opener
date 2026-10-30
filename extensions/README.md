# Extensions source

This directory is reserved for future PDF Magic Opener extension source
(implementation checklist §9.1, opener-0559). Git tracks files rather than
empty directories, so this README establishes a persistent source root
without introducing executable code.

It is a **source-only scaffold**, not an installed or enabled extension.
It does not define a build target, bundle, entitlement, launch handler,
scanner bypass, or app integration. Future extension implementations must
be reviewed and wired separately while preserving mandatory ClamAV scanning,
signature freshness, file-integrity and quarantine checks, and the
user-selected application preferences.
