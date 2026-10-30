# Offer a rasterized PDF copy when conversion is supported (opener-0313)

This optional Maximum-protection building block exposes
`maximum_sanitized_copy.offer_sanitized_pdf_copy(source_bytes)`. It returns
an immutable `SanitizedCopyOffer` only after a supported input has been
rendered into a **new, visual-only PDF** and the result passes strict
post-conversion inspection. Unsupported, encrypted, malformed, oversized,
unconvertible documents or missing macOS converter dependencies return
`None` and never become an offer. There is no unsafe fallback that simply
copies, edits or reserializes the original document.

The actual conversion runs in a separately compiled native
`maximum-sanitized-copy` executable built from `maximum_sanitized_copy.swift`,
using Apple's CoreGraphics PDF renderer. It reads bytes on stdin and
generates a PDF from only new raster images, not the source catalog,
actions, annotations, scripts, embedded files, arbitrary metadata, forms or
links. Only source page order, media-box dimensions and validated right-angle
rotation are retained.
Conversion is bounded to 16 MiB input, 16 pages, 2048-pixel longest
page side, 24 million total pixels, 32 MiB output, and 45 elapsed
seconds. Password-protected PDFs, cropped pages, and out-of-range dimensions remain
unsupported. Pages are emitted in source order with their media-box dimensions
and validated right-angle rotation (0, 90, 180, or 270 degrees) preserved.
The sanitizer also enforces a fixed 1 GiB process-group memory budget.
Linux applies a non-increasing hard `RLIMIT_AS` cap before converter `exec`
and monitors aggregate process-group RSS. On macOS, a watchdog checks the
process group's RSS every 50 ms and terminates it when the budget is exceeded.
The macOS watchdog is fail-closed but not an atomic kernel-enforced limit;
a native allocation can briefly exceed the target before its next poll.
Missing or unreadable memory measurements also stop conversion.

The rebuilt PDF is checked against the source page geometry before it can be
offered, so a missing, reordered, resized, or wrongly rotated page fails closed.

Every successful converted-copy offer carries a fixed, explicit
`conversionWarning` in `SanitizedCopyOffer.to_public_metadata()`, in the
successful `SanitizationDecision.to_dict()` result, and in the post-scan
`MaximumSafeCopyHandoff.to_public_metadata()` result. It identifies
conversion as a **meaningful document change** and explains the image-only
output, lost functionality and possible visual differences. It does not use
source-PDF strings or private file paths and cannot be suppressed through an
offer constructor. A future Maximum UI must prominently show the warning
alongside the save offer before a user decides to rely on the generated copy.
Failed or blocked conversions retain their existing diagnostics and do not
claim that a copy was generated. Maximum remains unavailable in the installed
Built-in-only application; this contract does not represent a presently
deployed conversion UI.

An offer is **not** a claim that the source or output is malware-free.
Rasterization loses searchable/selectable text, links, forms and other
features; unusual page content may render differently. **Flattening can
invalidate digital signatures.** A generated image-only PDF does not preserve
the original cryptographic signatures or their verification status and must
not be treated as a signed original; retain the untouched source for signature
verification. Sources with recognized signature flags or certification
permissions are already rejected before conversion, and the fixed offer
explanation warns about signatures for all other supported sources.
The offer has
`permits_open=False` and `needs_separate_scan=True`. Its PDF bytes remain
in memory: this module does not save files, launch a viewer, alter
quarantine, or approve a new document. A future Maximum UI can display
the fixed 'Save rasterized PDF copy' action only for a verified offer;
it must solicit explicit user save intent and route the resulting file
through the existing mandatory scan and file-integrity gate.

The installed application currently offers only Built-in protection.
Maximum is not selectable and has no complete end-to-end sanitized-copy
UI or coordinated isolated conversion orchestrator. This scoped task
does not enable it; production deployment must integrate the native
converter into a reviewed, OS-confined analysis pipeline before exposing
the action. In particular, these subprocess protections are not yet a
complete filesystem/network sandbox for an untrusted PDF renderer.

The dedicated CI suite validates fail-closed offer conditions, geometry
ordering, dimensions, right-angle rotations, and privacy on Linux. On macOS it
compiles the native helper and converts real generated PDFs, checking that
page order, media dimensions, rotation, JavaScript, and embedded attachments
are handled correctly. The active scanner,
signature updater, cached scan decisions, quarantine and user settings
are unchanged.


## Optional Save Sanitized Copy contract (opener-0544)

The verified in-memory offer now supports an explicit, optional action through
\`maximum_save_sanitized_copy.save_sanitized_copy(offer, destination, user_confirmed=True)\`.
The caller must present the fixed generated-content label and conversion warning
and receive affirmative confirmation for an absolute, user-chosen, new .pdf path.
Declining does nothing. A blocked or unverified conversion never becomes a save.

Saving stages only the reconstructed generated bytes through the existing
ownership-checked private temporary output lease. Before writing to the chosen
destination, it runs the **existing ClamAV gate** with current signatures, a
forced fresh scan and the normal integrity checks, but with **no application
selection, launch, or opened-document audit**. A clean scan is not permission
to open. The private staging lease is released after the save attempt; the
original source is never overwritten, copied, launched, or modified.

A successful save uses exclusive, no-follow creation with mode 0600. Existing
files (including symlinks), invalid destinations, missing confirmations and
scanner failures are refused without overwriting any content. Partial files
are removed only if their recorded inode still belongs to the save attempt.
The caller must still use the ordinary scanner when subsequently opening the
saved PDF. This is a future Maximum-only callable contract, **not** an
enabled Maximum profile or an installed SwiftUI save button; it introduces
no change to the Built-in scanner path or saved user preferences.
