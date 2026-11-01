# First-pass versus repeated ClamAV scan performance (opener-1086)

This **opt-in** benchmark compares the first standalone `clamscan` of a newly
created inert PDF fixture path (labeled **cold**) with an immediate repeat of
**that exact file** (labeled **warm**). Every scan is a new real `clamscan`
process with the existing trusted scanner flags and configured signature
location. It measures **end-to-end scanner-process wall time**, including
signature loading and shutdown. A calibration pair is discarded, then 3–7
matched pairs are recorded. Each pair uses its own fixture path.

```sh
python3 cold_warm_scan_benchmark.py --scanner /opt/homebrew/bin/clamscan --pairs 5
```

Specify `--database /existing/signatures` only when necessary. The output
includes median and nearest-rank p90 of first and repeat latency, median paired
`warm − cold` difference (negative means the repeat was faster), and median
per-pair cold/warm ratio (above 1 means faster repeat). A slower warm scan is
valid evidence and is never hidden. No fixed performance threshold is imposed.

**Important:** this is **not a physically cold disk-cache** benchmark: creating
a file can populate the OS page cache, the calibration pair may populate
scanner/signature caches, and the benchmark neither flushes system caches nor
restarts the machine. "Warm" does **not** mean a resident `clamd` engine:
ClamAV initializes again for every measurement. Do not interpret the ratios
as cold-boot speeds, benefits of a daemon, production PDF performance, or a
basis for changing security policy. Repeated measurements can vary because of
filesystem caches, scheduler load, signature database size and environment.

Only the repository's deterministic, harmless one-page PDF is written under a
private temporary directory. No user PDF, selected browser, preference, scanner
configuration, signature database or quarantine state is modified. It does not
run the application, open documents, or authorize opening. Scanner output and
paths are excluded from the report. Missing scanner/database, malicious/unclean
results, warnings, timeouts, partial pairs or invalid timing fail the *entire*
benchmark closed without reporting partial data.

A dedicated CI workflow runs contract regressions and **actual** `clamscan`
against an ephemeral, one-signature database on a disposable Ubuntu runner.
Those timings check correctness of the measurement rather than performance
of a full production signature set or macOS workstation.
