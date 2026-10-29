# Safe cleanup of temporary Maximum PDF outputs (opener-0325)

The future Maximum safe-copy handoff uses a private temporary file to let
the selected PDF viewer read an independently sanitized, newly scanned copy.
The file must **not** be deleted immediately after the launch call returns:
a browser or PDF viewer may still be reading it. Conversely, failed scans
and abandoned staging must not leave accessible partial PDFs indefinitely.

`maximum_temporary_output.stage_maximum_temporary_pdf(generated_bytes)`
creates one fresh private directory (`0700`) and an exclusive,
non-symlinked `safe-copy-<128-bit random hex>.pdf` (`0600`). The basename
is generated independently from 16 cryptographically secure random bytes
for each staging operation, not from a document name or predictable counter. It accepts only bounded
immutable PDF bytes and never derives any path from the PDF, its filename,
metadata, selected browser, or caller-provided directory. It returns an
`MaximumTemporaryOutput` ownership lease with `path` and `release()`.

The trusted caller holds the lease while the PDF is being scanned or read
by a viewer. On scan failure, cancellation or launch failure it calls
`release()` immediately. On successful handoff, it retains the lease
until the viewer has finished or the owning session ends. A `with`
block may manage short-lived uses; do **not** wrap an asynchronous viewer
handoff in a context that exits before the viewer reads the file.

Before deleting, `release()` verifies that the exact privately created
directory still exists, remains owned and `0700`, and has its original
device and inode. It opens the directory with `O_DIRECTORY|O_NOFOLLOW`
and deletes only the lease-recorded random filename after verifying its original inode,
owner, regular-file status and `0600` permissions. It removes the
directory only if empty: **no recursive deletion, wildcard, broad temp
directory sweep, arbitrary path input, or symlink-following cleanup**.
A replaced output or swapped directory fails closed and preserves any
unrelated file; it never deletes a different path merely to tidy a failed
handoff. Errors have fixed messages without filenames or PDF contents.

The module is an explicit lifecycle primitive, not an automatic timer or
an authorization to open. It does not alter the source PDF, the installed
ClamAV gate, quarantine, caching, browser preferences or the non-selectable
Maximum profile. PR #215 introduces the related safe-copy routing and is
the integration dependency: this cleanup primitive must be used by its
handoff lifecycle when that code reaches `main`. Ownership and viewer
lifetime, not arbitrary elapsed time, control deletion. Existing in-memory
raster conversion and analysis workers create no temporary PDF files.

The dedicated cross-platform CI workflow runs 11 tests for private
permissions, success/error cleanup, symlink and inode substitution,
forged leases, unknown extra files, partial writes, parallel sessions,
and noninterference with the active scanner. The result is not a clean
scan verdict and does not enable Maximum.
