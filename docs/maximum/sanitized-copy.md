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

## Future Maximum UI activity indicator (opener-0548)

A future Maximum interface can pass an optional `on_activity` callback to
`attempt_sanitized_pdf_copy`, `assess_sanitized_pdf_copy`, or
`offer_sanitized_pdf_copy`. Only after the input and converter have passed
preflight, the callback receives a fixed, path-free payload with
`phase="sanitizing"`, `isRunning=true` and the display label
**“Sanitizing document…”**. The activity remains running while the isolated
converter executes **and** while its output is rebuilt and verified.

A `phase="idle"`, `isRunning=false` event always clears the indicator
after an attempted conversion, whether it succeeded, crashed, timed out or
failed verification. Rejected preflight requests never claim sanitization
started. This is not a percent-complete estimate: both payloads explicitly
set `scanVerdict="notAssessed"` and `authorizesOpen=false`.
Presentation callback exceptions are ignored so they cannot change a
sanitizer outcome. No status is wired into the deployed Built-in-only panel
and this interface does not activate Maximum or bypass scanner safety.

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

## Saved-copy identity contract (opener-0547)

The optional future Maximum save dialog must clearly distinguish a generated
copy from its original. For a verified `SanitizedCopyOffer`, call
`offer.to_save_presentation(trusted_source_path)`: it returns a fixed
**“Generated sanitized PDF copy (not the original)”** label, an explicit
warning to retain the untouched original, `contentOrigin=generatedContent`,
`isUntouchedOriginal=false`, and a basename ending in
`-sanitized-copy.pdf`. This suggestion is derived only from the trusted
source filename, never from PDF metadata, and cannot equal that original
basename (including case-insensitive comparisons). Invalid source names
fail closed. No source directory or document bytes are exposed in this
presentation; ordinary public metadata stays path-free.

This is a **save-dialog presentation contract, not a save operation**. It
never writes a file or grants scanner/opening approval. The independently
assigned optional Save action (opener-0544) must require explicit consent,
create exclusively without overwriting the original or an existing file,
and preserve the mandatory separate scan gate. Maximum remains unavailable
in the installed Built-in application.
