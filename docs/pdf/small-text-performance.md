# Small text-based PDF performance benchmark (opener-1073)

This repeatable baseline measures **only the supervised, time-bounded PDF
structure-analysis stage**, not the installed ClamAV scan, the app's PDF opening
time, rendering, cache lookups, quarantine handling or any selectable protection
profile. Do not treat its results as end-to-end scan-to-open latency.

From the repository root, install the repository's reviewed optional PDF parser
dependency and run:

```sh
python3 -m pip install -r requirements-enhanced-pdf.txt
PYTHONPATH=. python3 small_text_pdf_benchmark.py --samples 5
```

The benchmark reuses the **synthetic one-page text PDF** from
`reference_pdf_collection.REFERENCE_PDFS[0]`, containing a simple Helvetica
text operation with a valid cross-reference table. Its size is under 4 KiB.
No downloaded, selected or private user PDF is read. The same in-memory bytes
are passed to the existing supervised `parse_pdf_structure_timed` worker
for one discarded warmup and 5–20 timed runs. The existing parser deadline,
process isolation and fail-closed behavior remain unchanged.

Output is bounded JSON with the fixture size, count, actual median and
nearest-rank 90th-percentile elapsed milliseconds. Every run must return the
expected single PDF 1.4 page, with a positive finite monotonic duration. Any
timeout, error, incomplete or unexpected result discards the **entire** report.
No filenames, file paths, document contents, scanner verdicts, user preferences
or opening authorizations are emitted or stored.

CI executes the actual small-text benchmark and its safety regressions. CI
hardware is transient and may vary: reported times are **measurements on that
specific runner**, not a representative macOS performance guarantee or a
performance threshold. For meaningful comparisons, repeat on supported
hardware with consistent workloads and record environment and variance
separately. The bundled protection UI remains deliberately unmeasured.

This is an **offline, observation-only test**. Nothing in the scanner gate,
opening pipeline, signature settings, cache, quarantine, file associations,
browser preferences or production protection behavior changes.
