# Recorded performance benchmark results (opener-1088)

These are **observed measurements**, copied from completed GitHub Actions job logs
on **2026-11-01 (UTC)**. They are not product speed guarantees, macOS production
baselines, cross-platform comparisons, or scan-approval evidence. The linked
jobs preserve the output and measurement context; values are intentionally
**not** stored as passing/failing speed thresholds.

## Observed synthetic CI workloads

| Workload / measured boundary | Recorded results | Samples and provenance |
| --- | --- | --- |
| [Medium PDF](medium-pdf.md), real supervised structure parser, synthetic 128-page, 4,209,653-byte document | Median **110.378 ms**; nearest-rank p95 **115.531 ms** | 3 runs after 1 warmup; Ubuntu, Python 3.11; [successful job](https://github.com/PDF-magic/opener/actions/runs/41333707830/job/124928967741) |
| [First versus repeated scan](cold-warm-scans.md), separate real `clamscan` process for each pass of an inert one-page PDF | Median first scan **10.113 ms**; repeat **9.941 ms**; median *paired* repeat-minus-first **+0.047 ms** | 3 pairs after 1 calibration pair; Ubuntu with a temporary one-signature database; [successful job](https://github.com/PDF-magic/opener/actions/runs/41333707914/job/124928968047) |
| [Scanner CPU](cpu-usage.md), one real `clamscan` child including signature loading | Median wall **20.506 ms**, child CPU **13.443 ms**, CPU-to-wall **65.59%** | 3 samples after 1 warmup; Ubuntu, temporary one-signature database; [successful job](https://github.com/PDF-magic/opener/actions/runs/41333707971/job/124928968680) |
| [ClamAV peak RSS](../peak-memory-benchmark.md), direct scanner-child high-water mark | Median **21.922 MiB**, maximum **22.000 MiB** | 3 samples after 1 warmup; Ubuntu, temporary one-signature database; [successful CI job](https://github.com/PDF-magic/opener/actions/runs/41333707915/job/124928969243) |
| [ClamAV repeated-startup experiment](../clamav-startup-benchmark.md), five separate scanner invocations versus one batched scanner invocation | Median five-process total **58.727 ms**; one-process batch **15.446 ms**; paired excess **43.281 ms** | 3 paired cycles; Ubuntu, temporary one-signature database; [successful CI job](https://github.com/PDF-magic/opener/actions/runs/41333707915/job/124928969243) |
| [Native scan-progress responsiveness](ui-responsiveness.md), real AppKit panel with synthetic sleeping scan child | Heartbeat median delay **5.972 ms**, p95 **10.417 ms**; Cancel dispatch median delay **6.936 ms** | 3 runs, 155 heartbeat observations; macOS runner; [earlier successful job](https://github.com/PDF-magic/opener/actions/runs/41333690994/job/124928956231) |

All rows except the native UI measurement were recorded at main commit
`1a8367a4df32961cbd02336b9c1607c975d1b190`. The UI observation was
recorded at `5c5df0b346c88a0a3914b2acf95c521565c0aa45`. A
[subsequent UI job](https://github.com/PDF-magic/opener/actions/runs/41333707859/job/124929035855)
on the newer main commit **failed without publishing measurements**. The
earlier successful UI number is retained as historical evidence, **not**
represented as a passing current baseline. Investigate that failure before
drawing responsiveness conclusions.

The first/repeat statistic is a *median of paired differences*: it need not
equal the difference of the separately reported medians. Neither pass
flushes OS filesystem caches or keeps a ClamAV daemon alive. The CPU
percentage describes one child process (not host CPU load), and the RSS
values describe the child process, not the entire application. A tiny
synthetic CI signature database can radically change scanner initialization
and memory usage relative to a real complete signature set. The UI child
does not perform malware scanning.

## Relative regression gate — separate paired run

The [same-runner regression policy](regression-thresholds.md) compares
synthetic medium-PDF structure parsing at base and candidate commits. A
[successful CI gate](https://github.com/PDF-magic/opener/actions/runs/41332780074/job/124926192340)
on 2026-11-01 recorded:

| Paired round | Baseline median | Candidate median | Baseline p95 | Candidate p95 | Outcome |
| --- | ---: | ---: | ---: | ---: | --- |
| 1 | 221.488 ms | 222.806 ms | 221.816 ms | 223.257 ms | No limit exceeded |
| 2 | 220.171 ms | 226.774 ms | 224.118 ms | 227.846 ms | No limit exceeded |

The gate passed with the existing **1.50× plus 15 ms median** and
**1.75× plus 25 ms p95** limits, requiring a confirmed breach in both
paired rounds. Its measurements are paired **within its own runner**;
do not compare their absolute milliseconds with the independent medium-PDF
CI job above. The threshold is a regression safeguard, not a promised latency.

## What this record does not establish

There is no verified representative **macOS, full-signature, end-to-end
PDF-open** latency result in this record. Nor are mock-clock unit-test numbers
valid speed evidence. Other opt-in benchmarks (including app launch,
signature-database loading, scanned-image PDF, large PDFs, Maximum
sanitization, and temporary disk usage) have their own harnesses or
documentation, but **no numerical results are asserted here** without a
specific completed measurement and provenance.

To add or replace a number, cite the completed run/job and source commit;
record the OS, hardware/runner, workload bytes/pages, scanner and signature
set, warmups, sample counts, timing metric/percentile, and any failure.
Use comparable conditions for trends. Do not turn these snapshots into
fixed cross-machine thresholds or use performance data to relax scanner
security, quarantine, signature freshness, or user preferences.
