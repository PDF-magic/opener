# Application bundle symlink containment (opener-0368)

Before hashing a selected macOS application bundle, the scanner enumerates its
entries and resolves **every** symbolic link strictly against the canonical
application root. File or directory links resolving outside that root are
rejected with the existing path-free error. Missing symlink targets and cycles
also fail closed; non-strict resolution no longer treats them as safe.

This validation occurs before reading bundle contents or accepting a cached
clean verdict, executing ClamAV, or handing the application to a launcher. It
repeats during the existing file-integrity checks. Legitimate in-bundle file
and directory aliases remain supported; standalone-file alias behavior and
user preferences do not change.

The new cross-platform regression verifies absolute, relative, directory and
chained escapes; unresolved and cyclic links; valid internal aliases; and
rejection before cache lookup, scanner invocation or opening. The existing
ClamAV version, signature freshness, quarantine, caching and handoff policy
are unchanged.
