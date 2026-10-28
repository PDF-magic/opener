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
actions, annotations, scripts, embedded files, metadata, forms or links.
Conversion is bounded to 16 MiB input, 16 pages, 2048-pixel longest
page side, 24 million total pixels, 32 MiB output, and 45 elapsed
seconds. Password-protected PDFs and rotated/cropped/out-of-range pages
are unsupported rather than automatically simplified.

An offer is **not** a claim that the source or output is malware-free.
Rasterization loses searchable/selectable text, links, forms and other
features; unusual page content may render differently. The offer has
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

The dedicated CI suite validates fail-closed offer conditions and
privacy on Linux. On macOS it compiles the native helper and converts
real generated PDFs, checking that JavaScript and embedded attachments
from the original do not enter the rasterized copy. The active scanner,
signature updater, cached scan decisions, quarantine and user settings
are unchanged.
