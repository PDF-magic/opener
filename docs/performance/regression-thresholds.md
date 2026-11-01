# Same-runner performance regression thresholds (opener-1087)

The first enforceable performance gate measures only the **existing deterministic
128-page, ~4 MiB, inert medium-PDF workload** through the real supervised
PDF structure-analysis worker. It is **not end-to-end** opening latency, ClamAV
throughput, app-launch time, or representative production performance. Scanner
security and user preferences are outside this comparison.

## Thresholds

For each metric, a candidate exceeds the limit if:

`candidate > max(baseline × relative factor, baseline + absolute grace)`

| Metric | Relative factor | Absolute grace | Evidence |
| --- | ---: | ---: | --- |
| Median wall time | 1.50× | 15 ms | 5 completed runs after one warmup |
| Nearest-rank p95 wall time | 1.75× | 25 ms | 5 completed runs after one warmup |

A regression fails the dedicated required CI job only when **the same metric
exceeds its limit in both paired rounds**. A single-round breach is reported as
unconfirmed, with a successful exit for investigation; two passing rounds pass.
The first round measures baseline then candidate; the second candidate then
baseline. The paired checkouts share the **same runner**, Python version,
installed parser dependencies and immediate measurement window. Grace protects
against tiny timing fluctuations; two-round confirmation reduces false failures
from transient CI contention. These are initial conservative *relative*
engineering guardrails, not guaranteed response-time service levels.

## Evidence safety and comparability

The CI job checks out the exact target base and proposed head SHAs separately,
with no saved credentials. It refuses to compare changes to the fixture
generator or timed benchmark protocol. Both checkouts explicitly use the
**candidate's reviewed parser pin**, installed once on the same runner, so a
security-only dependency pin update can proceed without defeating the paired
application-code regression gate. Because *both* revisions use the upgraded
dependency, this comparison does **not** measure the isolated performance
effect of upgrading the dependency itself; that requires a dedicated
dependency-version benchmark. It still tests changes to the measured PDF
parser or supervisor against identical benchmark and dependency environments.
An incompatible upgraded parser fails the checks instead of authorizing
opening or silently skipping the comparison.

The policy evaluator requires exactly two complete baseline/candidate pairs,
the same fixture byte count, exact expected stage/workload, 128 pages, one
warmup, five runs, non-authorizing results, and finite positive median/p95
values. Missing files, malformed/duplicate JSON keys, invalid samples or
incomparable workloads block CI with no partial decision. Measurements are
ephemeral on disposable runners; no user documents, signature databases,
preferences or production scan/open paths are accessed or modified.

Review the job's aggregate JSON for the individual limits and outcomes.
A confirmed breach should be investigated and fixed rather than raising
thresholds without an evidence-backed review. For benchmarks of real macOS
opening, large PDFs, raster conversion, scanner CPU/memory and UI responsiveness,
no portable base/head performance gate is claimed yet: those measurements
need representative reproducible baselines and dedicated calibration before
such thresholds would be trustworthy.
