# Remove active functionality from the sanitized PDF (opener-0315)

The optional Maximum sanitized-copy flow, introduced by
[PR #209](https://github.com/PDF-magic/opener/pull/209), now runs the output
of its macOS raster converter through
`maximum_active_content_removal.remove_active_pdf_functionality()`.
Only afterward can `offer_sanitized_pdf_copy()` return an in-memory offer.

The removal stage **constructs a second fresh PDF** rather than editing or
cloning any source PDF dictionaries. It accepts only a strict, bounded
rasterized candidate with one decodable image XObject per page, reconstructs
the image from actual RGB pixels, and creates new pages with only the
`/Im0 Do` image-draw operation. No input `/Contents`, source catalog,
annotations, automatic or JavaScript actions, forms/XFA, multimedia, links,
embedded files, names trees, launch actions, other resources, metadata,
attachments, or original compressed image streams are copied. The output is
reparsed with strict PDF validation before the offer is created.

Conversion is **required before removal**: this is not a safe substitute
for an actual renderer for arbitrary PDFs. Unsupported, unreadable,
encrypted, malformed, oversized, multi-image or otherwise unconvertible
candidates fail closed and produce no offer, and no original PDF is returned.
Bounds inherited from the converter remain: 16 pages, 2048 pixels per side,
24 million pixels total, and 32 MiB for the input and output PDF. It
does not interpret source PDF JavaScript or submit forms.

This is a lossy operation: searchable text, forms, attachments, links, page
interactivity, color profiles and other features will not survive. Raster
images can still present visual deception or trigger reader vulnerabilities;
this is not a malware-clean verdict or a guarantee against PDF exploits.

This stage neither saves nor opens the result. It retains
`permits_open=False`, `needs_separate_scan=True`, and the installed
Built-in ClamAV, quarantine, file integrity and user preferences untouched.
Maximum remains non-selectable. A future reviewed OS-confined conversion
pipeline and explicit user save flow must scan the generated file before
opening. Isolated page rendering in opener-0314 stays separate.

The dedicated `test-maximum-active-content-removal.py` checks JavaScript
and action dictionary removal, form/attachment stripping, original page
content stream exclusion, exact pixel fidelity, multiple pages, malformed
or oversized inputs, and scan-gate noninterference. The existing sanitized
copy workflow runs these tests and the real native CoreGraphics conversion
on Linux/macOS, with a pinned Pillow dependency for decoding pixels.
