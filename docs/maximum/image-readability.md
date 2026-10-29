# Image readability after Maximum PDF conversion (opener-0516)

This is a **fidelity regression test**, not a scanner control or a new
conversion path. The optional Maximum CoreGraphics converter remains unchanged.

The test constructs two harmless, synthetic PDF pages containing distinct,
Flate-compressed RGB image XObjects placed at known PDF page coordinates.
Each image contains saturated colors, high-contrast 6-pixel checker cells and
fine 1-pixel diagram strokes. No third-party pictures or private user content
are needed. The source PDF is checked with the pinned pypdf parser to confirm
both expected images are present and unchanged before conversion.

On macOS CI, the test compiles the actual Swift CoreGraphics conversion worker,
calls the real offer_sanitized_pdf_copy entry point and decodes each **generated**
PDF page's image in memory. For each page, it checks the expected 2x raster
dimensions, crops the known source-image placement, then compares the downsampled
output to its original reference image. Mean RGB error, checkerboard dark/light
contrast and page-order comparisons fail if images are missing, swapped,
washed out, severely blurred, or replaced by solid blocks. These conservative
metrics are visual legibility proxies, not comprehensive image-recognition
or accessibility guarantees. Separate text readability and color tests remain.

Linux CI executes the deterministic fixture and metric tests, including
negative controls for blanks, blur, fading, incorrect page images and uniform
fills; only macOS executes actual CoreGraphics conversion. The Maximum
sanitized-copy workflow runs both platforms with pinned pypdf and Pillow.

The original PDF and generated PDF are held in memory. No PDF viewer is
launched; no copy is written to disk, and scanner settings, quarantine,
signatures, cache, destination handoff and user preferences are untouched.
SanitizedCopyOffer.permits_open remains false, it still requires a **fresh
ClamAV scan**, and Maximum is still nonselectable. A passed image fidelity
test never indicates that either PDF is safe to open.
