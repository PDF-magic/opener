# Maximum worker memory limits (opener-0309)

This task enforces memory limits **inside the separate Maximum PDF analysis
worker** introduced in [PR #203](https://github.com/PDF-magic/opener/pull/203).
It does not activate the planned Maximum tier or modify the deployed ClamAV
scanner, quarantine, cache, file integrity, browsing or user preferences.

`maximum_memory_limits.impose_maximum_worker_memory_limit()` runs before
loading any PDF parsing module. Its immutable **1 GiB resident-memory target**
comes from the planned isolated-behavior stage's trusted resource policy, not
from untrusted PDF content or saved settings.

- **Linux:** the OS enforces a hard, non-increasing 1 GiB `RLIMIT_AS`
  (address-space) ceiling in the worker. Memory allocations that exceed it
  fail inside the worker and yield no permission to open.
- **macOS:** because dyld and Python reserve more virtual memory than their
  resident working sets, a 1 GiB `RLIMIT_AS` cannot be used safely. The
  worker instead applies an OS hard **8 GiB data-segment safety ceiling** and
  checks peak resident memory with a 50 ms real-time signal timer. Resident
  usage greater than 1 GiB raises a memory-limit failure and causes the child
  to stop without a report or clean verdict. The timer is a best-effort
  watchdog, not an atomic kernel RSS reservation; rapid mmap allocations
  may briefly exceed the target before a signal is delivered. Future native
  Maximum worker integration should consider stronger platform entitlements.
- **Any other OS, missing limit capability or failed setup:** refuse to
  inspect; no unconstrained fallback.

Existing tighter inherited limits are preserved. PDF bytes continue through
the isolated worker's in-memory stdin and numeric evidence-only response.
Existing CPU, wall-time, no-core-dump and no-output-file limits remain
separate and unchanged. Failure propagates through the parent worker's fixed,
path-free failure result. It cannot authorize a PDF to open.

The new macOS/Linux GitHub Actions workflow validates the OS limits, a
real rejected oversized allocation on Linux, simulated resident overage,
invalid/unavailable limits, and the actual isolated analysis integration on
both platforms. The full repository CI jobs remain unchanged.

This PR is intentionally stacked on the upstream process-isolation work in
[PR #203](https://github.com/PDF-magic/opener/pull/203) and does not copy
its PDF parsing/worker implementation or duplicate filesystem confinement
in [PR #204](https://github.com/PDF-magic/opener/pull/204).
