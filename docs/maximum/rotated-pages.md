# Rotated-page fidelity tests (opener-0521)

The `test-maximum-rotated-pages.py` suite verifies that the optional Maximum
sanitized-copy conversion preserves **visible page orientation**, not just a
copied `/Rotate` dictionary value.

The deterministic PDF source consists of six nonsquare pages with explicit
0°, 90°, 180°, 270°, and −90° rotations, plus a page that inherits 90° from
the parent `/Pages` node. Every page contains asymmetric vector-only
corner markers (red, green, blue, yellow) and a page-specific center marker.
No source attachments, scripts, external files, or private documents are used.

On both Linux and macOS, the source fixture is parsed to verify page order,
source dimensions, inherited and normalized rotations, and vector drawing
operators. The standalone pixel metric also rejects wrong rotations, mirrored
pages, cropped edges, blank pages, and swapped pages. Its expected image is
independently generated with Pillow, not rendered from the sanitizer.

On **macOS**, the test invokes the real compiled CoreGraphics
`maximum_sanitized_copy.offer_sanitized_pdf_copy` worker. It reads each
returned raster-only output page, checks the exact media box and normalized
rotation, checks the one embedded RGB image's 2× pixel dimensions, then
checks all five page-specific markers at the **expected displayed positions
after /Rotate**. The 90° and 270° cases must have swapped displayed width
and height. Pure metadata copying, horizontally mirrored pages, page swaps,
blank or cropped output, and incorrect raster orientation fail the test.

This is a fidelity regression suite, not a malware detector, full viewer
conformance test, or admission rule. The installed ClamAV scanner, signature
requirements, quarantine and handoff gates, sanitized output re-scan
requirement, user preferences, and non-selectable Maximum tier remain
unchanged. Both existing `maximum-sanitized-copy.yml` CI jobs run the suite;
Linux skips only actual CoreGraphics conversion.
