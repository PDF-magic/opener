# Malformed PDF structure detection (opener-0293)

The passive Enhanced-stage function inspect_pdf_malformed_structures(contents: bytes)
examines only immutable PDF bytes, using the installed maintained pypdf
strict parser. It validates an exact PDF header, final startxref/EOF framing,
a classic cross-reference table at the indicated offset, the size and catalog
in the trailer, every indexed object header and the basic page tree.
It checks indexed objects even when they are unreferenced by any page.

Malformed object offsets or generations, damaged or missing trailers and page
trees, unsupported compressed/xref streams, encrypted documents, missing
dependencies, uninspectable objects and resource overruns fail closed with a
single fixed error. No original bytes or private content are returned.

Limits: 16 MiB input, 4,096 indirect objects, 1,024 pages and bounded trailer
matching. The returned frozen result exposes only object/page counts and
always has malformed=false and permits_open=false. A failure raises an
exception; it must never be treated as a clean result.

This is deliberately distinct from the general structure parser in PR #179
and object-relationship inspector in PR #182. This stage checks physical
syntax and cross-reference alignment rather than validating the complete
object graph, incremental revision chain, JavaScript, forms, annotations or
embedded files. A valid document using unsupported xref streams is conservatively
rejected, not silently approved.

**Not activated:** The installed Built-in ClamAV scan, cache, quarantine,
signature enforcement, file handoff, configuration and user preferences remain
unchanged. Enhanced is still nonselectable. Production use will require the
separate budgeted, time/memory-isolated Enhanced pipeline and every mandatory
Standard scan check; this result alone never authorizes opening.
