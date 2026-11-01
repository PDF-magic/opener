# Standalone ClamAV peak memory benchmark (opener-1081)

This **opt-in observation-only** experiment measures the peak resident set
size (RSS) of an actual standalone `clamscan` process scanning the repository's
existing, inert, one-page synthetic PDF. It complements, but does **not**
replace, the structural PDF parser's separate RSS benchmark in
`pdf_parser_memory_benchmark.py`. This is **not** the combined application's
memory, concurrent-scanner memory, a PDF viewer/rendering benchmark, or an
end-to-end scan-to-open measurement.

## Run on a test machine

With an **existing, trusted** local scanner and complete signature directory:

```sh
python3 peak_memory_benchmark.py \
  --scanner /opt/homebrew/bin/clamscan \
  --database "/path/to/existing/clamav/signatures" \
  --samples 3
```

The scanner must be one of the project's allowlisted executable paths. This
tool does not discover a new scanner from PATH or install/update signatures.
It never scans selected, downloaded or private user PDFs. It creates the
bounded synthetic fixture in a disposable directory, performs one warmup and
1–10 recorded runs, and deletes the fixture afterward. It passes the **same**
ClamAV flags as the established standalone startup benchmark; that command
does not replace the production scanner gate.

On Linux/macOS, `wait4` returns each **direct child clamscan process's**
`ru_maxrss`. Linux reports KiB; macOS reports bytes. Both are converted to
MiB, and the result includes process initialization, signature loading and
the scan. Each recorded run gets its **own process-level high-water mark**,
not the parent's lifetime resource maximum. The JSON gives median and maximum
of successful recorded peaks, after the warmup is excluded.

A nonzero exit, incomplete clean output, stderr warning, timeout, unsupported
platform or invalid sample causes **the entire benchmark to fail without
printing partial data**. On timeout, the dedicated scanner process group is
killed and reaped. The benchmark never opens a PDF, records a clean verdict,
writes settings, mutates the signature database, uploads telemetry or uses
results to authorize any action. JSON excludes document bytes, paths and
scanner output.

CI first checks the sampling, process accounting and failure contracts with
disposable test doubles. It also runs **real** `/usr/bin/clamscan` against a
minimal, temporary synthetic signature database on an Ubuntu runner. This
measures actual process RSS, but it is **not representative of a full production
signature database or macOS hardware**. Actual memory depends on host
architecture, engine/version, signature set, cache state and document
complexity; compare only similar environments. CI enforces successful
measurements, not a numerical RSS threshold or performance claim.

No application, scanner, quarantine, cache, user preference or protection
profile behavior is changed.
