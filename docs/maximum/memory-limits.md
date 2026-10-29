# Maximum worker memory limits (opener-0309)

This task imposes memory limits **inside the separate Maximum PDF analysis
worker** introduced in [PR #203](https://github.com/PDF-magic/opener/pull/203).
It does not activate Maximum, modify the Built-in ClamAV scanner, or change
quarantine, file integrity, cache, browser, or user preferences.

The worker calls `maximum_memory_limits.impose_maximum_worker_memory_limit()`
before any PDF parser is imported. The immutable **1 GiB target** comes from
the planned isolated-behavior resource policy; it cannot be changed by a PDF
or saved settings.

- **Linux:** a hard, non-increasing **1 GiB `RLIMIT_AS`** address-space
  ceiling enforced by the operating system. Allocations beyond the ceiling
  fail in the worker and cannot authorize a PDF to open.
- **macOS:** the current supported interpreter rejects hard memory ceilings
  through `RLIMIT_AS`, `RLIMIT_DATA` and `RLIMIT_RSS`. Instead, the
  child must install a 50 ms signal timer to check its **peak resident memory**
  against 1 GiB. Exceeding the target or being unable to install the timer
  aborts inspection, without an opening verdict. This is a **best-effort
  watchdog, not an atomic OS-enforced memory cap**. A large native allocation
  could temporarily exceed the target before Python services the signal.
  A native OS-sanctioned memory boundary would be necessary before claiming
  strict macOS kernel enforcement of a one-GiB RSS ceiling.
- **Other platforms or missing limit support:** refuse to run without a
  memory guard; there is no unlimited fallback.

Existing, stricter limits are not relaxed. CPU, wall-time, no-core-dump and
no-output-file limits remain unchanged. PDF bytes continue over worker stdin
and only sanitized numeric evidence is returned. All worker setup and
inspection failures produce the pre-existing fixed fail-closed report.

A dedicated GitHub Actions workflow validates the limits on Linux and macOS,
including a real rejected oversized Linux allocation, macOS watchdog overage
simulation, unsupported-platform failure, child bootstrap with the actual
pinned PDF parser, and the real isolated-analysis test suite.

This is deliberately stacked on [PR #203](https://github.com/PDF-magic/opener/pull/203);
the filesystem-confinement PR [#204](https://github.com/PDF-magic/opener/pull/204)
and network-blocking work remain outside this task.
