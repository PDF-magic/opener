# Generated safe-copy identification (opener-0513)

The optional Maximum sanitizer now labels its verified raster-built copy as
**generated content, not the untouched original PDF**. The fixed visible
action is **Save generated sanitized PDF copy**.

`SanitizedCopyOffer.content_origin` and
`MaximumSafeCopyHandoff.content_origin` hold the immutable allowlisted
value `generatedContent`. Their `to_public_metadata()` methods expose only
fixed display fields, including `isUntouchedOriginal: false`, without
source paths, document bytes, filenames or untrusted metadata.

The optional generated-copy re-scan verifier and Maximum safe-copy handoff
refuse a tampered origin marker. They retain mandatory independent ClamAV
scanning, exact-byte verification, quarantine and launch protections; the
original document is never used as a fallback for failed conversion or scan.

This marker is deliberately **out of band**. The existing metadata-removal
contract strips source and producer metadata, so no `/Info`, `/ID`, XMP,
source-identifying attribute, visual watermark or page alteration is added
to the generated PDF. The source remains unchanged. The installed Built-in
scanner, settings and user customizations are unchanged. Maximum remains
unselectable until separate prerequisites are ready.
