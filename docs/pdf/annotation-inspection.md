# PDF annotation inspection (opener-0290)

The optional `pdf_annotations.inspect_pdf_annotations(contents: bytes)` stage
checks page `/Annots` arrays, individual annotation subtype and rectangle,
flags, direct `/A` actions, `/AA` action hooks, destinations, appearances,
and file-attachment specifications. It accepts immutable in-memory PDF bytes
and uses the maintained `pypdf==5.9.0` already installed for existing Enhanced
tests. It does not open files, evaluate JavaScript, follow links, execute
actions, decode appearance streams, or extract embedded file content.

An immutable result contains annotation counts, recognized subtype categories,
and whether direct actions, additional actions, destinations, appearances and
potentially active annotation types were encountered. It never contains user
content, filenames, link targets, or script bodies. `permits_open` is always
`False`; any annotation requires other independent Enhanced stages to inspect
its untrusted content. Unknown annotation subtypes, malformed structures,
unresolvable references, encrypted PDFs, unsupported object streams and
resource-limit breaches fail closed with one fixed, path-free error.

Limits: 16 MiB document, 1,024 pages, 4,096 indexed indirect objects,
2,048 annotations, at most 64 appearance states per appearance dictionary,
and 32 additional action hooks per annotation.

This is **not** an active Enhanced protection policy. It does not modify
the Built-in ClamAV scan, scanner failure handling, existing cache or
quarantine rules, browser selection or PDF handoff. Other planned stages own
full action-body validation (including chains), attached-stream scanning,
and sandboxed execution-time/memory budgets. See the related external-action
and automatic-action work; those stages cannot be bypassed by this report.
