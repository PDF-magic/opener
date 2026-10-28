# Structural ambiguity detection (opener-0294)

`pdf_structure_ambiguity.inspect_pdf_structure_ambiguity(contents)` is a
**read-only, fail-closed inspection building block** for future Enhanced PDF
protection. It takes immutable bytes, not file paths. It does not run or
supersede ClamAV and never returns an opening authorization.

The inspection requires the already-tested `pypdf==5.9.0` dependency in
current main's Enhanced embedded-file CI stage. With strict PDF parsing it
eagerly checks the referenced and unreferenced traditional cross-reference
objects for duplicate dictionary keys, verifies that each live cross-reference
offset matches the declared object number and generation, refuses two objects
claiming the same byte offset, and requires a complete final `startxref` /
`%%EOF` trailer with no untrusted trailing content. Valid prior EOF markers
in incremental PDFs are **not** automatically treated as conflicts.

Malformed, ambiguous, encrypted, unavailable-parser, compressed-object or
oversized inputs fail closed with a fixed path-free error, rather than a clean
verdict. Input is capped at **16 MiB** and the active cross-reference count at
**4,096** objects. Passing the inspection means only that these specific
ambiguities were not observed, **not** that the document is safe or complete.

The maintained parser being reviewed in [PR #179](https://github.com/PDF-magic/opener/pull/179)
and object-relationship checks in [PR #182](https://github.com/PDF-magic/opener/pull/182)
have separate scopes. [Opener-0291](https://github.com/PDF-magic/opener/pulls)
will examine revision history; this stage does not claim to validate that
history or resolve all PDF structure ambiguities. A future integration must
coordinate parser-version changes, enforce execution-time and memory isolation,
and run **all** existing Standard and Built-in safety gates before enabling
Enhanced. Installed scanner operations, clean cache, OS quarantine, browser
preferences, and launcher behavior are unchanged.
