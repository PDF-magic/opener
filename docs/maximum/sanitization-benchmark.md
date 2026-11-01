# Benchmark Maximum raster sanitization (opener-1079)

Run this **opt-in diagnostic** on macOS after compiling the repository's
trusted native CoreGraphics converter. It measures real sanitization, not
ClamAV, downloading, quarantine removal, or PDF-opening latency.

```sh
swiftc -O maximum_sanitized_copy.swift -o maximum-sanitized-copy
python3 -m pip install --disable-pip-version-check 'pypdf==5.9.0' 'Pillow==11.3.0'
PYTHONPATH=. python3 maximum_sanitization_benchmark.py --samples 3
```

The workload is the fixed, harmless one-page text PDF from
`reference_pdf_collection.REFERENCE_PDFS`, held entirely in memory.
Every measured attempt passes through
`maximum_sanitized_copy.attempt_sanitized_pdf_copy`, including source
admission, the real supervised native CoreGraphics raster converter,
post-render active-content removal, strict page/output validation, and
generation of an immutable, separate-scan-only offer. A warmup conversion
is discarded; 3–10 completed runs yield a median and nearest-rank p90
in milliseconds, along with sample count and in-memory sizes. Results
reflect the host's macOS, hardware, process startup, and caching and should
not be compared as if obtained from identical systems. No absolute speed
target is imposed on shared CI runners.

**Fail closed:** missing/untrusted converters, unsupported inputs, crashes,
timeouts, invalid outputs, and incomplete samples fail with no JSON result
and no partial timings. Linux regression tests use deterministic injected
attempts **only** for contract assertions; their ticks are not performance
measurements. The macOS CI job compiles the real converter and executes
the real benchmark after its dependencies are installed.

The benchmark does not read user documents, accept source paths, save an
output PDF, make network requests, open any file, assign malware verdicts,
change user preferences, or alter the mandatory scanner. The installed
application still cannot select Maximum. These isolated prototype timings
must not be copied into the bundled protection performance estimates as
representative deployment measurements.
