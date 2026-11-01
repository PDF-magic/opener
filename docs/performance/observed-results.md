# Recorded performance benchmark results (opener-1088)

This is a **dated, reproducible snapshot of actual measurements**, not a speed
guarantee or a performance claim about installed copies. All observations
below came from successful GitHub Actions benchmark steps on **1 November
2026**, using disposable hosted CI runners and synthetic, non-user PDF
fixtures. No values below come from mocked clocks or test assertions.

Most results are from the main-branch commit
`1a8367a4df32961cbd02336b9c1607c975d1b190`. The UI result is
from the preceding main commit
`5c5df0b346c88a0a3914b2acf95c521565c0aa45` and is labeled
separately because the newer UI workflow run failed. Follow each source
link to its original measured JSON and workflow logs.

## Observed measurements

| Benchmark ID | Exact workload and runner OS | Recorded samples | Observed result | Primary evidence |
| --- | --- | ---: | --- | --- |
| `small-text` | 1-page, 589-byte inert text PDF; supervised parser; Ubuntu | 5 | 78.670 ms median; 81.597 ms p90 | [CI job](https://github.com/PDF-magic/opener/actions/runs/41333707915/job/124928969306) |
| `medium-pdf` | 128-page, 4,209,653-byte inert PDF; supervised parser; Ubuntu | 3 | 110.378 ms median; 115.531 ms p95 | [CI job](https://github.com/PDF-magic/opener/actions/runs/41333707830/job/124928967741) |
| `embedded-objects` | 256 image objects and 24 attachments; passive inspector; Ubuntu | 3 | 29.097 ms median; 29.308 ms p90 | [CI job](https://github.com/PDF-magic/opener/actions/runs/41333707915/job/124928969306) |
| `enhanced-structure` | 1-page, 589-byte inert reference; strict Enhanced stage; Ubuntu | 3 | 52.340 ms median; 53.334 ms p90 | [CI job](https://github.com/PDF-magic/opener/actions/runs/41333707915/job/124928969306) |
| `scanner-startup` | Five one-page fixtures; separate processes versus one batch; Ubuntu | 3 cycles | 58.727 ms median five-process total; 15.446 ms median one-process batch | [CI job](https://github.com/PDF-magic/opener/actions/runs/41333707915/job/124928969243) |
| `peak-memory` | Standalone ClamAV scan with minimal synthetic signatures; Ubuntu | 3 | 21.922 MiB median child peak RSS; 22.000 MiB maximum | [CI job](https://github.com/PDF-magic/opener/actions/runs/41333707915/job/124928969243) |
| `cpu-usage` | Standalone ClamAV with minimal synthetic signatures; Ubuntu | 3 | 13.443 ms median child CPU; 20.506 ms median wall | [CI job](https://github.com/PDF-magic/opener/actions/runs/41333707971/job/124928968680) |
| `cold-warm` | First scan and immediate repeat of same inert PDF; Ubuntu | 3 pairs | 10.113 ms median first; 9.941 ms median repeat | [CI job](https://github.com/PDF-magic/opener/actions/runs/41333707914/job/124928968047) |
| `app-launch` | Debug SwiftUI preferences app, spawn to first onAppear; macOS | 3 | 387.667 ms median; 456.493 ms p90 | [CI job](https://github.com/PDF-magic/opener/actions/runs/41333707915/job/124929061199) |
| `ui-responsiveness` | 25 ms AppKit heartbeat during synthetic scan child; macOS | 3 | 5.972 ms median callback lateness; 10.417 ms p95 lateness | [CI job](https://github.com/PDF-magic/opener/actions/runs/41333690994/job/124928956231) |

Results are **per-row aggregates**, not runs of one shared end-to-end test.
In particular, the medians of first and repeat ClamAV scans cannot be
subtracted to recover a paired median. That run independently reported a
**+0.047 ms median paired warm-minus-first difference** and a **0.995 median
first/repeat ratio**; it does not establish an improvement from caching.
The five-process versus one-batch startup experiment is **not** a daemon
comparison or a reason to replace the production scanner. Scanner CPU is
direct-child CPU time (not total-host utilization); its wall time includes
signature loading. Memory is the direct child process's RSS high-water mark,
not app-wide memory. UI callback delay is not real click latency or ClamAV
throughput. The application launch row measures the Debug preferences window
only, not PDF opening.

The scanner measurements use a deliberately tiny temporary signature database
on Ubuntu rather than production signatures on a Mac. Parsing cases use
different worker/process boundaries and workload sizes; **do not compare their
medians as if they measured the same operation**. Per-row p90/p95 values are
nearest-rank statistics from small samples and can vary with runner load,
hardware, caches and software versions. The UI observation comes from a
different successful run and commit than the other results; it is not evidence
that the later failed workflow passed.

## Reproduce, extend and interpret

See the individual benchmark methodology pages:
[small text](../pdf/small-text-performance.md),
[medium PDF](medium-pdf.md),
[embedded objects](../pdf/many-embedded-objects-benchmark.md),
[Enhanced structure](../enhanced/structural-benchmark.md),
[scanner startup](../clamav-startup-benchmark.md),
[peak memory](../peak-memory-benchmark.md),
[CPU usage](cpu-usage.md),
[first versus repeat](cold-warm-scans.md),
[app launch](app-launch.md), and
[UI responsiveness](ui-responsiveness.md). Each page explains how to
reproduce its opt-in benchmark and the intended measurement boundary.

For performance regressions, use the
[paired, same-runner threshold policy](regression-thresholds.md) instead of
treating the numbers above as universal pass/fail limits. Further workloads
such as scanned image-based PDFs, full signature-database loading and
production end-to-end opening have **no representative results in this
snapshot**. Do not substitute synthetic or mocked test values for
uncollected measurements.

These results **never authorize opening a PDF**, establish a malware verdict,
change the active scanner gate, remove quarantine, install a daemon, enable
optional protection, or override existing user preferences.
