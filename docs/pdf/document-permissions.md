# Passive PDF document permission inspection (opener-0461)

The optional `pdf_document_permissions.inspect_pdf_document_permissions(bytes)`
examines standard PDF permission declarations without decrypting content,
verifying signatures, or authorizing opening. Document permissions are
**untrusted claims**, not scanner verdicts or independently enforced rights.

For Standard Security Handler encrypted PDFs, the inspector reads the signed
32-bit `/Encrypt /P` bitmask and reports recognized print, modify, copy,
annotate, form-fill, accessibility extraction, assembly and high-quality print
flags. **It never supplies a password or calls decrypt.** The catalog cannot
be inspected without decryption, so `catalogInspected=false` explicitly
means *not inspected*, not *absent*. Unknown security handlers, malformed
flags, and unsupported cross-reference/object streams fail closed.

For unencrypted PDFs, the shared strict structure and stream length parser
runs first. The inspector examines catalog `/Perms` dictionaries for
`/DocMDP`, legacy `/UR` and `/UR3` declarations. A declared DocMDP
modification level of 1, 2 or 3 may be reported if structurally valid in a
`/Reference /TransformParams /P` entry. This stage **does not verify
signatures**, ByteRange values, certificate trust, cryptographic integrity,
or enforce any claimed modification restrictions.

Immutable output contains only trusted fixed identifiers and bounded
integers; `signatureVerified=false` and `authorizesOpen=false` always.
No passwords, signature bytes, document content, paths, or PDF-controlled
strings are returned. Failures use one sanitized fixed error.

Bounds: 16 MiB PDF input, 32 indirect resolutions and 16 signature
transform references. All installed Built-in ClamAV scan, quarantine,
signature and clean-cache safeguards, saved preferences, and application
handoff are unchanged. Enhanced remains non-selectable.

CI covers encrypted permissions without decryption, valid and malformed
signature declarations, bounded values, parser errors and scanner isolation.
