# Verify installed ClamAV dependencies (opener-0963)

The **Allow and Open** installer now checks the scanner and signature updater
immediately after the optional, explicitly authorized Homebrew ClamAV
installation, and also when a compatible ClamAV package already exists.

The read-only verification runs **before installing opener scripts or writing
signature directories and preferences**. It requires an executable regular
`clamscan` at one of the three supported scanner paths, plus a companion
executable `freshclam` in the **same** installation prefix. Homebrew symlinks
to executable regular files are supported. Only these fixed paths are eligible;
an arbitrary command on `PATH` cannot substitute for the runtime scanner.

Both tools must answer a bounded `--version` probe and identify a stable,
supported ClamAV 1.4 or 1.5 release. Their major/minor release branches must
match. Missing, nonexecutable, unverifiable, unsupported or mismatched tools
cause a nonzero exit with a fixed actionable message; raw subprocess output,
scanner paths, and private user data are never emitted. Verification performs
no scan, signature update, download, mutation, or browser handoff.

This does **not** replace the signature update or its staged database
validation, nor the runtime admission checks for scanner version, fresh
signatures, file integrity, quarantine, and PDF handoff. The installer still
requires explicit consent before any Homebrew package operation and preserves
existing user settings. Passing the dependency probe is **not** evidence of
a clean scan or sufficient to open any file.
