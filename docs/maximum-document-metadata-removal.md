# Strip unnecessary document metadata from sanitized PDF copies (opener-0507)

The optional Maximum raster-copy pipeline must not carry source document
metadata into a newly generated visual-only PDF. The post-render rebuild in
\`maximum_active_content_removal.remove_active_pdf_functionality()\` creates a
fresh \`PdfWriter\` from bounded raster pixels, and now explicitly disables
pypdf's default \`/Info\` dictionary and file identifier.

The rebuilt output excludes:
- conventional trailer \`/Info\` fields such as title, author, subject, keywords,
  creator, producer, creation date and modification date;
- catalog or page XMP \`/Metadata\` streams;
- the trailer \`/ID\` document identifier;
- page \`/PieceInfo\` and \`/LastModified\` entries.

The final-output verifier independently rejects \`/Info\`, \`/ID\`, catalog/page
XMP, and page-level private metadata. This prevents an output with leftover
metadata from passing verification even if a future writer or conversion path
changes its defaults. Regression tests place private marker values in Info,
XMP and the file identifier, verify none survive raster reconstruction, and
verify each metadata-bearing output is rejected by the structural gate.

This is metadata removal, not a malware verdict or a promise of anonymity:
visible text and images remain visible in the rasterized pages. The generated
copy still has to pass the existing verification and mandatory separate scan.
The change does not activate Maximum protection, save or open files, modify
the installed scanner, or change quarantine, signature, clean-cache, or
user-preference behavior.
