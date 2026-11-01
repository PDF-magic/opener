# Benchmarking Enhanced structural analysis (opener-1078)

Run `PYTHONPATH=. python3 enhanced_structure_benchmark.py --samples 5`.
The CI workflow also runs a three-sample benchmark and regression tests
with the pinned optional `pypdf` dependency. Output is JSON.

The benchmark measures **actual strict structure parsing** through
`pdf_structure_parser.parse_pdf_structure`, wrapped by the existing
`AdditionalAnalysisTimer` for the `pdfStructure` stage. Two reproducible,
harmless in-memory PDF workloads are used: the existing one-page text
reference and a generated 32-page blank PDF. Each sample runs in a fresh
subprocess with a 30-second parent timeout. Fixture generation and process
startup are excluded. One warmup per case is discarded, then 3–10 samples
produce median and nearest-rank p90 milliseconds.

The report includes only fixed labels, page/byte counts, timings, and
`authorizesOpen: false`. An invalid, incomplete, failed, or timed-out
sample aborts the entire benchmark without partial output or private errors.
This subprocess is **not** an untrusted-document sandbox: the benchmark
accepts generated corpus bytes only. It never inspects user files or changes
ClamAV, quarantine, cache, protection profiles, or opening permissions.
Other Enhanced stages and end-to-end scanning/opening are not measured.
