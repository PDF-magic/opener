# Read-only first-run scanner installation check (opener-0975)

The first-run welcome screen checks for an executable regular `clamscan` at the
same three fixed locations used by the runtime scanner, and for an executable
`freshclam` companion in the chosen scanner's installation prefix. Homebrew
symlinks are supported when they resolve to actual executable regular files.
The status distinguishes a missing scanner, a missing/inaccessible updater,
and a detected pair. **Check Scanner Again** refreshes the status without
changing saved preferences or starting an installer.

This is an **installation-presence diagnostic**, not a ClamAV version or
malware-signature verification, and never a security verdict about a file.
A detected pair may still have an unsupported version, stale signatures, or
another runtime failure; the installed scan gate independently enforces
compatible versions, valid recent signatures, and the clean-scan requirement
before opening any PDF. No file is scanned or opened, no executable is run, no
installation or network action occurs, and no browser, Finder action, PDF
association, or selected protection profile is modified.

`test-first-run-scanner-installation.swift` covers absent, non-executable,
partial, mismatched-prefix, symlink, and directory installations using only
temporary fixtures. The portable first-run regression checks UI wiring and
safety boundaries. Both are required CI checks.
