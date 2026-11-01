# Measuring ClamAV signature database load time (opener-1072)

This is an **opt-in, read-only performance experiment**. It does not change
the installed scanner, signature updater, scan cache, preferences, or opening
policy. The existing fail-closed `clamscan` admission gate remains authoritative.

## Run on a test Mac

Use an existing and fully installed ClamAV shared library and signatures.
From the repository root, for a typical Apple Silicon Homebrew installation:

```sh
python3 signature_database_load_benchmark.py \
  --library /opt/homebrew/opt/clamav/lib/libclamav.dylib --samples 5
```

The default database is the application's installed signatures directory.
The optional `--database` path must contain exactly one nonempty regular
`main.cvd` or `main.cld` and one `daily.cvd` or `daily.cld`.
Symlinked database directories or main/daily entries are rejected, and no
signature files are changed. The library must be one of the explicitly
allowlisted, installed absolute paths. No library is searched from PATH.

Each run performs one discarded warmup and 3–7 samples. Every sample uses a
new bounded Python subprocess and a fresh libclamav engine. It calls
`cl_init`, creates the engine, directly times **`cl_load`** (database load)
and **`cl_engine_compile`** (preparing signatures), then frees the engine.
The sample's measurements exclude Python startup, dynamic library loading,
and engine allocation; they include file I/O and any OS cache effects.
Each subprocess has a 180-second limit. A load/compile error, timeout,
unexpected output, mismatched signature count or version aborts the entire
experiment without reporting partial results.

Output contains only schema/scope, ClamAV version, signature count, sample
count, and aggregate milliseconds (median and nearest-rank p90 for load,
median compilation and ready-to-scan preparation). No filesystem paths,
signature contents, user PDFs, raw stderr, or per-sample filenames are
published. There are **no bundled empirical results**. Unit tests use
synthetic timing values, not live signature-load performance evidence.

## Interpretation

Record the hardware, ClamAV and signature versions, database size, filesystem,
sample conditions, and cold/warm cache state outside the JSON before
interpreting comparisons. Warmup means ordinary output is primarily a
**warm-cache** measurement, not first-install/first-boot load time.
Because this uses libclamav directly, it is not a complete `clamscan`
startup-time, scan-time, memory, or user-opening benchmark; see
[the separate scanner startup benchmark](clamav-startup-benchmark.md).
Performance observations cannot authorize opening a PDF, relaxing signature
freshness requirements, or replacing the installed scanner.
