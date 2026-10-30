# Choose a permanent sanitized-copy destination — opener-0545

The optional Maximum workflow can ask the user to select a permanent PDF
destination using the macOS AppKit helper `maximum_safe_copy_destination.swift`.
Invoke its standalone `MaximumSafeCopyDestinationCommand` **only** after the
user chooses the separate **Save Sanitized Copy** action and a verified,
in-memory `SanitizedCopyOffer` is available. It presents a native
`NSSavePanel` that lets the user choose the directory and filename, with
`sanitized-copy.pdf` as a fixed, source-independent suggestion. The accepted
file must have the PDF type; no original filename or PDF metadata enters the
dialog. The panel permits directory creation but cannot silently pick a
destination.

On confirmation the helper writes only the chosen absolute PDF pathname,
terminated with a NUL byte, to stdout. On Cancel, missing selection, invalid
selection, or unexpected command-line arguments it fails without returning
a destination. **It never creates, deletes or overwrites a PDF**, scans a file,
opens a viewer, or changes preferences. Treat the returned pathname as
untrusted input, not as permission to write: the eventual optional save
implementation (opener-0544) must separately protect the source file, reject
unsafe destinations, handle overwrite consent, perform safe copying and require
the existing scanner gate before any opened output. It must never interpret
a destination choice as a clean scan or authorize opening the original.

The installed application still offers Built-in only. This helper is not
wired into the unavailable Maximum UI; no user-facing save action is exposed
by this prerequisite alone. Temporary safe-copy retention and cleanup are
separate checklist tasks. The main scanner, converter and user customizations
are unchanged.

Both macOS CI workflows compile the command and run injected-dialog tests.
The tests cover the native dialog configuration, explicit approval, Cancel,
missing or non-PDF/file selections, and absence of output-file writes without
displaying a real GUI in an unattended runner.
