# Vector graphics fidelity regression (opener-0519)

This test-only change checks whether the optional Maximum-protection
CoreGraphics converter preserves the **visible shape and location** of source
PDF vector graphics after creating a raster-only sanitized copy.

Two deterministic vector-only in-memory pages exercise distinct filled
rectangles, polygons, diamonds and a cubic-Bézier oval; a separately stroked
Bézier curve, diagonal and thin hairline rule; open and closed paths; and a
clipped oversize fill that must not leak outside its clipping rectangle. Both
pages contain no embedded images, text layer, private documents or scripts.

On Linux, the test checks the actual pypdf fixture operators and runs
independent Pillow reference graphics through a region/color, stroke,
placement and whitespace/clipping metric. Negative controls reject
blanked or removed shapes, page swaps, horizontal shifts and out-of-bounds
clipping. A local PyMuPDF render was also used to sanity-check the metric.

On macOS, CI **compiles and runs the real CoreGraphics converter** via
`maximum_sanitized_copy.offer_sanitized_pdf_copy`; no mock renderer
satisfies this test. It validates both returned pages, dimensions and order,
absence of searchable text, one image XObject per page, expected 2x raster
resolution, correct vector-shape colors/positions, stroke details and clipped
white background. The test is intentionally visual: original vector path
objects are flattened to image pixels, not preserved as editable vectors.

The pixel thresholds allow antialiasing and minor rendering differences.
This test does not prove exact Bézier continuity, all PDF color profiles,
arbitrary transparency/blends, print-ready vector editability, visual
equivalence for every PDF, or document safety.

Only `test-maximum-vector-graphics.py`, this documentation and the existing
`maximum-sanitized-copy.yml` test matrix are changed. The installed Built-in
ClamAV scanner, quarantine and integrity protections, saved user preferences,
scanner cache, browser handoff and optional sanitizer implementation are
unchanged. The Maximum profile remains unselectable. A generated copy
still requires a **separate malware scan** and never authorizes opening.
