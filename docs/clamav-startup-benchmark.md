# ClamAV startup benchmark and persistent-daemon decision gate (opener-0375)

**Decision: retain the installed per-request clamscan scanner.** No trustworthy
benchmark of repeated clamscan initialization costs has yet been collected
on representative user hardware and workloads. A disposable Ubuntu CI runner
now records a genuine but deliberately nonrepresentative minimal-signature
baseline; those values must not be used to justify a production engine change. There is no clamd migration,
no daemon launcher, no socket, no new service, and no change to how files are
opened. Merely configuring a timeout or running the CI tests is **not** a
performance measurement. Existing successful clean-cache reuse already avoids
some duplicate scans and must be considered in a realistic workload.

## Safe opt-in baseline measurement

On a test machine with an already installed, updated ClamAV scanner and its
signatures, from the repository root, run manually:

    python3 scanner_startup_benchmark.py --scanner /opt/homebrew/bin/clamscan --files 5 --cycles 3

Use one of the three executable paths already supported by the installed
scanner, or explicitly supply the existing signature directory using the
--database option. No executable is discovered from PATH. The script creates
five synthetic PDF-like files in a temporary directory, performs one discarded
warmup, and measures three paired cycles of (a) five *separate* clamscan
processes and (b) one clamscan process recursively scanning those same
five files. The phase order alternates to reduce warm-cache order effects.
All invocations use the installed scanner's **standalone-PDF ClamAV options**
and the configured signature directory. Each invocation is bounded to 180
seconds; an error, timeout, warning, incomplete output or abnormal exit
aborts the experiment **without publishing timing data**.

The JSON summary contains only sample counts and measured milliseconds
(first invocation, median/p90 of the individual one-shot invocations, and
aggregate paired cycles), not scanner output, filesystem paths, file contents
or user document details. The first invocation is not a guaranteed cold-cache
start; an individual one-shot duration includes signature loading, scanning,
and process termination, not process launch alone. The two metrics are the median total time of the repeated
one-shot invocations and the median total time of a single batched invocation.
The difference may reflect signature loading, cache effects and other
per-invocation costs. **It is not an isolated process-start duration, a
production end-to-end latency estimate, a clamd benchmark, nor proof that a
persistent daemon would be faster.** No data is bundled or reported to an external service. CI's mocked
unit-test clocks are not measurements. A separate real-ClamAV CI step on a
disposable Ubuntu runner executes this opt-in harness with a temporary,
one-signature database, prints aggregate numbers only to its job log, and
destroys that database afterward. These are real invocations but are **not
macOS or production-database measurements**. CI enforces completion and safe
output, never a timing threshold or claimed speedup.

## Conditions before considering clamd

1. Collect **real** repeated clamscan measurements on supported macOS
   systems with documented ClamAV engine version, signature revisions,
   CPU/memory/storage environment, cold and warm starts, benign fixture
   characteristics and scanner flags. Include independent replicates and
   variation, not only one median or a synthetic CI value.
2. Measure representative individual PDFs, application bundles, sequential
   requests, concurrent requests, and cache-hit frequency, while **never
   uploading, logging or benchmarking private user files**. A tiny synthetic
   fixture baseline alone cannot justify a production architectural change.
3. If the repeat-startup overhead is materially significant to observed
   opening latency, run a **separate opt-in controlled clamd prototype**
   with equivalent effective malware policy, database freshness, file limits,
   scan timeouts, encrypted/oversized alerts, concurrency and failure
   handling. Compare full distributions, steady-state RAM/CPU, cold-start
   costs and operational complexity; a one-process batch is not a daemon
   substitute or daemon speed estimate.
4. Before any production proposal, review ownership and authentication of
   a local daemon socket, daemon availability/restart, signature reloads,
   stale results, symlinks, file identity, quarantine retention, timeout and
   cancellation of descendant processes, isolation, user permissions and
   the fail-closed opening contract. A missing, crashed or untrusted daemon
   must **never** authorize opening or a clean-cache entry.
5. Require a separately scoped implementation, regression tests, explicit
   opt-in or justified deployment plan, successful macOS and Linux CI, and
   a new reviewed PR before changing the production scan engine.

**Until these prerequisites are satisfied, the project intentionally
continues using clamscan.** Existing scanner limits, malware detection,
signature freshness, quarantine, cache policy, opening destinations, parent
lifetime, cancellation and user preferences are unchanged.
