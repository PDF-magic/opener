# Scanned-document fidelity after Maximum PDF conversion (opener-0518)

This is a targeted **fidelity regression test**, not a scanner or OCR stage.
It covers scanned PDFs whose **entire page is a bitmap**, rather than an
embedded diagram surrounded by vector text (covered separately by
opener-0516) or vector multi-column layouts (opener-0517).

The deterministic fixture creates two distinct full-bleed image-only pages.
Each page has a pale scan-paper background, small rasterized printed text,
1-pixel ruled lines, corner registration marks and grayscale halftone
details. The second page additionally contains a colored approval stamp.
The embedded image XObjects are Flate-compressed and fill the media boxes.
The source is validated with pypdf to ensure that each page has exactly one
bitmap, correct pixel dimensions, no searchable text layer, and distinct
unmodified source image bytes. No private documents or OCR data are needed.

On **Linux**, the test validates the source and checks that its image
comparison metric rejects white pages, fading, heavy blur, aggressively
downscaled thumbnail replacements, swapped pages and clipped registrations.
The metric compares per-page RGB difference, source-ink/paper contrast,
the distinct bottom-right scan stamp, and all four corner markers.
These are bounded visual-fidelity proxies, not guarantees of legibility
for every real-world scan.

On **macOS**, the existing sanitizer CI compiles the actual CoreGraphics
conversion worker and the test calls
`maximum_sanitized_copy.offer_sanitized_pdf_copy` on the source PDF.
It reads only the returned in-memory PDF, verifies two ordered media boxes
and no searchable text, and inspects each generated page's **actual**
2x raster image after downsampling to source resolution. The image must
retain printable ink, white paper contrast, color/gray details, page
registration marks and its page-specific stamp. The conversion itself is
not mocked in that test.

No sanitizer code, PDF viewer, files on disk, ClamAV signature settings,
quarantine controls, preferences or opening pipeline are modified. The
returned sanitized-copy offer still has `permits_open=False` and
`needs_separate_scan=True`, and Maximum remains unavailable for selection.
Passing the fidelity test does **not** establish that the original or
generated document is safe; the generated copy requires its own scan.
