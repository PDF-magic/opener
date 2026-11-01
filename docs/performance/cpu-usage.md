# Isolated scanner CPU measurements (opener-1083)

This optional tool measures CPU consumed by **one standalone `clamscan` child
process** using POSIX `wait4` resource accounting. It includes process startup,
signature loading, scanning a real inert one-page PDF, and process shutdown;
it is **not** end-to-end PDF opening time or a CPU prediction for real PDFs.
It does not scan user documents, change installed scanner settings, replace
antivirus checks, or authorize opening.

From the repository root, with the existing trusted ClamAV installation and its
signature database already available, run:

```sh
python3 cpu_usage_benchmark.py --scanner /opt/homebrew/bin/clamscan --samples 5
```

Use `--database /path/to/existing/signatures` if the default signature
location does not apply. The opt-in run accepts 3–7 measured samples, discards
one warmup and scans only a disposable copy of the repository's known inert
reference PDF. The same ClamAV flags as the existing startup benchmark are
used. No daemon, network access, preferences write, signature update, or
external telemetry is introduced.

Results include median user CPU milliseconds, kernel CPU milliseconds, their
combined median and p90, wall milliseconds, and median CPU percentage. CPU
percentage is `100 × (user CPU time + system CPU time) / elapsed wall time` for
each scan, then the median across samples. It may exceed 100% for multithreaded
workers and is **not** host-wide CPU utilization. Each sample is reaped and
accounted independently, avoiding the cumulative resource accounting of other
child processes. A failed, timed-out, partial, or warning-bearing scan discards
the entire report. Paths, scanner output, PDFs, and signature content are not
included in the JSON.

CI executes real `clamscan` with a temporary, one-signature test database on a
disposable Ubuntu runner and runs a separate regression suite. This measures
**including signature database initialization**, so the tiny CI signature set
is not representative of an installed production signature database or macOS
hardware. There is deliberately no CPU-performance threshold; only successful,
verifiable accounting is required.
