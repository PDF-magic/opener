# Transparency fidelity regression (opener-0520)

This **test-only** change verifies that the optional Maximum sanitized PDF
converter preserves the visible appearance of transparent PDF elements while
flattening source pages into opaque, image-only pages. The output is not
expected to preserve transparency operators or an alpha channel: visually
correct compositing against the converter's white page background is the
acceptance criterion.

A deterministic two-page synthetic PDF contains native PDF transparency,
not a pre-rendered approximation:

- Page 1 overlays an opaque blue rectangle with a 50%-opacity red rectangle,
  creating distinct opaque, overlapped, and white-backed translucent regions.
  An RGB image XObject uses a grayscale `/SMask` with 0%, ~50%, and 100%
  alpha stripes, testing image transparency in addition to vector alpha.
- Page 2 overlays an opaque yellow rectangle with a 50%-opacity blue
  rectangle using the PDF `/Multiply` blend mode. It checks both overlapping
  and white-backed regions and catches mistaken normal blending.
- Both pages have untouched white regions and different visual compositions,
  detecting incorrect page order, opacity and background flattening.

On Linux and macOS, the fixture is structurally inspected using pypdf to
confirm its `/ExtGState /ca`, `/BM /Multiply`, image `/SMask`, and content
operators. Independent Pillow RGB-composition reference pixels are checked
with interior landmarks, and negative controls deliberately introduce
opaque replacements, blank pages, swapped pages and normal-blend mistakes.

On macOS, the existing sanitized-copy CI compiles the real CoreGraphics
converter and runs it on the actual generated PDF. The regression examines
the returned in-memory PDF, demands two raster-only pages at the expected
2x size, verifies that no searchable text remains, and compares pixels at
both pages' transparency landmarks with conservative 38-channel tolerance
to account for renderer/color-rounding differences. This is an actual
conversion test—not a mocked sanitizer—and no source PDF goes to disk.

No sanitizer or viewer production code is changed. The scanner's mandatory
ClamAV gate, quarantine, cache, signature checks, user preferences and
file-opening workflow remain untouched. Maximum remains unselectable.
`SanitizedCopyOffer.permits_open=False` and
`SanitizedCopyOffer.needs_separate_scan=True` continue to hold. Passing
the fidelity test is **not** a malware-clean verdict or a permission to open
or distribute either the source or converted document.
