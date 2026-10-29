# Multi-column document fidelity (opener-0517)

This regression suite tests two-column and three-column PDF layouts across
two pages of the existing optional Maximum sanitized-copy converter. It is
**test-only**. No scanner, sanitizer, user preference or opening behavior is
changed.

The deterministic in-memory source PDF uses Helvetica vector text and
distinct RGB header and footer bands positioned in independent columns.
Each page contains two text baselines per column. The source is validated
with pypdf to establish that both columns (page 1) or all three columns
(page 2) contain the expected distinct text without embedded raster images.

On **macOS**, the test invokes the actual compiled CoreGraphics converter
through `maximum_sanitized_copy.offer_sanitized_pdf_copy`. It verifies that
both output pages retain their dimensions and order, contain exactly one
raster image each at the expected **2×** resolution, and have no extracted
searchable text. In those real output pixels it checks:

- Each column's upper and lower color bands remain at its expected position
  with tolerant per-channel color measurements.
- Both lines in *every* column retain detailed dark glyph-like ink, not
  simply a solid filled block or missing text.
- The gutters between columns and outer margins stay white; content is not
  stretched, merged, overlapped or shifted into another column.
- The two-column and three-column pages retain distinct compositions, catching
  swapped pages and dropped columns.

On Linux and macOS, source-fixture tests and negative-control image metrics
reject blank output, missing text, shifted content and gutter bleed. These are
conservative **visual fidelity proxies**, not OCR, semantic reading-order
checks, accessibility verification or proof that arbitrary PDFs will render
faithfully. The emitted copy is intentionally raster-only and loses search
and selection of the source text.

The existing `.github/workflows/maximum-sanitized-copy.yml` runs this suite
on both platforms; only the macOS job performs actual CoreGraphics PDF-to-PDF
conversion after compiling the native worker. The tests neither launch a
viewer nor write user documents to disk. `SanitizedCopyOffer.permits_open`
remains false, generated copies still need a **fresh ClamAV scan**, Maximum
remains unselectable, and all original quarantine, cache, signature,
destination and user-customization protections remain intact.
