# Preserve supported PDF color appearance (opener-0500)

The optional Maximum sanitized-copy pipeline preserves supported visual colors
while rebuilding a document from newly rendered pixels. The native CoreGraphics
renderer uses an explicit sRGB bitmap color space rather than a display-dependent
DeviceRGB context. Supported DeviceRGB, DeviceGray, and DeviceCMYK source
content is therefore converted into a stable sRGB rendering before the page is
flattened; the final reconstruction stores the decoded pixel values in fresh
8-bit DeviceRGB image objects.

This is **visual color preservation**, not preservation of the original PDF
color-management metadata. Source color-space dictionaries, ICC profile
objects, output intents, spot-color separations, overprint settings, and source
image dictionaries are intentionally not copied. Transparency is composited
against the renderer's white page background. The resulting copy remains
raster-only and loses searchable text and interactive features as documented
by the sanitized-copy contract.

The macOS-native regression in `test-maximum-sanitized-copy.py` creates vector
regions using RGB, grayscale, and CMYK operators, sends them through the entire
sanitized-copy pipeline, and checks the final image's interior pixel colors.
The existing `maximum-sanitized-copy.yml` workflow already compiles the native
converter and runs this test suite on macOS. This task does not enable Maximum,
change the installed scanner, or alter the separate-scan and user-save gates.
