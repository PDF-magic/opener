# Detect unusual PDF indirect-object counts (opener-0464)

`pdf_unusual_object_counts.inspect_pdf_unusual_object_counts(contents)`
is a **passive**, optional Enhanced-stage inspection primitive. It counts
active, numbered indirect objects in the strict parser's current classic
xref index, including unreachable/orphaned indexed objects. It compares
those counts with the independently parsed page count, and reports
anomalies instead of asserting that every document within the hard parser
limits is ordinary.

## Review signals

The detector returns the sorted, fixed anomaly codes:

- `high_object_count`: at least **1,024** indexed objects (below the
  separate 4,096-object hard inspection cap).
- `high_objects_per_page`: strictly more than **128 indexed objects per
  parsed page**.
- `sparse_object_ids`: the highest numbered active object is at least
  **256** and at least **eight times** the number of indexed objects.

These are conservative heuristic **review signals**, not an indication of
malware or evidence of PDF integrity by themselves. Rich PDFs with annotations,
fonts, resources, complex graphics, and historical incremental revisions can
legitimately exceed these thresholds. The relative test is about density
of indirect objects, not the size of any particular object. Stream sizes
are inspected separately by `pdf_embedded_object_sizes.py`; xref graph
correctness and page-tree consistency by `pdf_object_relationships.py`.

A frozen `PDFUnusualObjectCounts` contains the active object count,
parsed page count, highest indexed object number, and fixed anomaly codes.
Its detached JSON report always contains `authorizesOpen: false`.
No file paths, object contents, strings, URLs, scripts or filenames
are returned. The absence of a flag never authorizes opening.

## Explicit limits, unsupported features and fail-closed behavior

This inspector first invokes the shared strict PDF structure parser on
immutable in-memory bytes (16 MiB input and 1,024 pages maximum).
It validates every indexed object's number, generation and offset.
At most **4,096** numbered objects are accepted, matching the existing
object-index inspection ceiling. A malformed or encrypted PDF, missing
dependency, malformed trailer `/Size`, invalid object index/offset,
or excessive object count is rejected with a fixed, path-free error
rather than a false-empty report.

**Compressed object streams** (`xref_objStm`) are deliberately refused,
not undercounted: their indexed objects need an independently reviewed,
bounded counting path before they may produce this particular evidence.
The shared strict parser continues to support formats that it can inspect;
this optional stage never claims it inspected objects it could not count.

This detector does not activate Enhanced, bypass the installed ClamAV scan,
override quarantine or clean-cache gates, change preferences, or send PDFs
to the network. Tests use generated PDFs, including a deliberately sparse
classic xref file, and exercise the existing parser and object-relation
regression suites in dedicated CI.
