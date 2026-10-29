# Passive embedded PDF file-type inspection (opener-0455)

`pdf_embedded_file_types.inspect_pdf_embedded_file_types(contents)` uses the
existing strict in-memory PDF structure parser and bounded attachment discovery
from `enhanced_embedded_files.py`. It discovers specifications reachable through
catalog `/Names /EmbeddedFiles` trees, document and page associated-file
(`/AF`) arrays, and `/FileAttachment` annotations. It decodes embedded bytes
only in memory through the existing raw/Flate-only bounded decoder.

## Evidence returned

The independent inspector identifies common file signatures (PDF, JPEG, PNG,
GIF, ZIP-family including OOXML containers, OLE compound files, ELF, PE/DOS,
Mach-O, WebAssembly, ambiguous Java/fat Mach-O, shebang scripts, HTML, XML,
RTF and plain UTF-8 text). Unrecognized or undecodable bytes are classified
as `unknown_binary`, never as a clean file. It does **not** execute files,
interpret embedded documents, traverse archive contents, or establish that a
recognized signature is safe. In particular, a ZIP signature does not prove
an archive is valid, and a container may hide a macro or executable.

For declared types it compares recognized embedded stream `/Subtype`
MIME declarations and file-specification `/UF` or `/F` extensions to
actual magic-byte categories. Unknown/unspecified MIME or filename extensions
are not treated as proof of a mismatch. Mismatch counters capture
potential misleading declarations without disclosing the filename or MIME
text. These are **indicators for review**, not definitive malware verdicts.

A frozen `PDFEmbeddedFileTypes` result returns the total attachment count,
bounded inspected-byte count, sorted **fixed** detected-type identifiers,
unknown and executable counts, and separate MIME and extension mismatch
counts. `to_dict()` produces a detached JSON record with
`authorizesOpen: false`. Neither filenames, paths, attachment contents,
untrusted MIME values nor parser errors are returned.

## Failure behavior and limits

A 16 MiB document limit from the strict parser applies. This stage permits
at most 32 discoverable attachments, 4 MiB decoded bytes per attachment
and 16 MiB cumulatively. Unsupported compression, malformed declarations,
encrypted PDFs, missing parser support, invalid attachment references, or
exceeded limits result in a fixed, content-free
`PDFEmbeddedFileTypeError`, not an empty or clean result.

This stage **does not activate Enhanced** or replace the existing
`enhanced_embedded_files.inspect_embedded_files` ClamAV inspection, which
remains a separate security requirement. It never modifies the installed
ClamAV scanner, signatures, quarantine, clean cache, destination app,
user preferences, or browser handoff. Detecting a type cannot permit opening
a PDF. The existing full scan and separate validation requirements remain
mandatory. CI uses generated benign PDF fixtures to exercise type detection,
mismatches, associated files, annotation attachments, limits, and scanner
isolation.
