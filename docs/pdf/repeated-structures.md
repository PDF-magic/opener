# Detect suspiciously repeated PDF structures (opener-0466)

`pdf_repeated_structures.inspect_pdf_repeated_structures(contents)` is a
passive, optional Enhanced-stage inspection primitive. It fingerprints
indirect dictionary and array shapes to identify unusually repeated
structures, without treating repetition alone as proof of maliciousness.

## Review signal

The detector normalizes scalar values to their types, preserves PDF name
values, and treats indirect references as references without resolving them
again during fingerprinting. It returns counts only; PDF-provided strings,
stream bytes, object identifiers, URLs, and paths are not included in the
report. Ordinary `/Page` and `/Pages` dictionaries and stream objects are
excluded so that page count and repeated stream payloads do not by themselves
trigger this heuristic.

A structure is flagged for review if one shape appears at least **128** times,
or if one shape appears at least **32** times and all objects in repeated
shape groups together account for at least **25%** of inspected structural
objects. Smaller repeated groups remain visible as counts but are not labeled
suspicious. These are conservative heuristics, not a malware verdict: valid
PDFs may contain repeated resources, annotations, or other reusable structures.

## Limits and safety boundary

The shared strict parser first validates the in-memory PDF under its existing
16 MiB input and 1,024-page limits. This detector inspects at most **4,096**
indexed objects, **65,536** structural nodes, and **64** direct nesting levels.
Encrypted documents, compressed object streams, malformed xref entries,
invalid object offsets, unavailable dependencies, and over-budget structures
fail closed with one fixed, content-free error rather than producing a
false-empty report.

Stream payloads are not decompressed or interpreted. The immutable result
contains only bounded counts and always reports `authorizesOpen: false`.
The detector does not activate Enhanced or Maximum protection, alter the
installed ClamAV scan gate, change preferences, modify files, or open PDFs.
