# Large PDF benchmark (opener-1075)

This repeatable **large PDF parsing benchmark** uses the existing, validated
[large valid PDF corpus](large-valid-corpus.md) without downloading documents or
reading user files. It measures how long strict `pypdf` structure loading **and
traversal of every content stream** takes on two **16 MiB+** inert PDFs:

- `single-large-stream`: one page, a real content stream containing 17 MiB of harmless whitespace.
- `many-large-pages`: 256 pages with independent 64 KiB content streams.

Run from the repository root after installing `requirements-enhanced-pdf.txt`:

```sh
python3 large_pdf_benchmark.py --case all --runs 3
```

The script creates each PDF in memory and uses a **fresh child process per
sample**, capped at five runs per case and 90 seconds per worker. It verifies
page counts, each page's content prefix, and exact content-stream sizes so the
measured path is actual decoding and traversal, not merely checking a PDF
header. The JSON reports median fixture construction time, median strict
parse-and-traverse time, and the maximum child **peak process RSS** in MiB.
The peak includes Python, the generated document and the parser. It is not an
isolated parser allocation metric. Partial, failed, warned or timed-out child
runs produce **no report**, rather than a misleading fast measurement.

Results depend on host CPU, memory, Python version, `pypdf` version and
system load. Record these alongside repeated samples on representative
machines. CI runs a one-sample, 256-page synthetic **smoke benchmark** and
regression tests, not a performance budget or reproducible hardware baseline.
No speed claims or regression thresholds are established from hosted CI.

**Safety and scope:** This is not an end-to-end PDF-opening benchmark and
**not** a ClamAV scan, native file handoff or malware assessment. It cannot
authorize opening, bypass the default scanner, change the 16 MiB optional
structure-analysis budget, clear quarantine, update caches or modify preferences.
A large PDF valid under the strict parser may still exceed the optional
structure stage's admission limit; that stage must continue to report
`sizeLimit` without authorizing opening. Full real-world scanner latency,
especially signature loading and decompression workloads, requires a separately
reviewed measured workflow with the production scanner and representative
hardware; no such latency is inferred here.
