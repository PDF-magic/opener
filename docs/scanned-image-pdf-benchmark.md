# Scanned image-based PDF benchmark (opener-1076)

This **opt-in** experiment measures **scan-process latency** for an image-based
PDF. It is **not full PDF-opening latency**, a browser/rendering benchmark,
or evidence that a file is safe to open. The installed app and the required
ClamAV gate remain untouched.

## Workload and measurement

`scanned_pdf_benchmark.py` constructs a deterministic, valid PDF 1.4 in a
private temporary directory. Each US Letter page consists of a full-page,
150-dpi, 1,275 × 1,650 grayscale raster image XObject with Flate compression,
a simple image-drawing content stream and no native text or OCR. Page marks
are synthetic, not a real person's scanned document. There are no active
actions, network links, attachments or embedded scripts. The page count
is limited to 1–4, and files are deleted on completion or failure.

Invoke manually on a system with an already installed trusted ClamAV binary
and existing local signatures:

```sh
python3 scanned_pdf_benchmark.py \
  --scanner /opt/homebrew/bin/clamscan \
  --pages 2 --runs 5
```

Use `--database` only when the normal local signature directory differs.
The program refuses other scanner executables and missing signatures. It uses
the existing standalone-PDF ClamAV flags, one warmup scan and 3–7 measured
separate scanner invocations. Each scan has a 180-second subprocess timeout.
Any detection, nonzero exit, missing/mismatched clean output, warning, timeout
or invalid measurement rejects the **entire** report. Only aggregate median
and nearest-rank p90 milliseconds, fixed workload metadata and the number of
completed samples are emitted. No input pathname, PDF contents, raw scanner
output, user document or opening verdict appears in the report.

Do not compare machines or claim real-world performance without recording
machine specifications, ClamAV and signature versions, filesystem/cache
conditions and repeated workload measurements separately. Scanner startup
cost is included. A synthetic image-heavy PDF cannot represent all real
photocopied or high-resolution scanned PDFs. This experiment **does not**
instrument filesystem selection, live scanner orchestration, GUI launch,
quarantine handling, rendering or browser handoff.

## CI and safety boundary

`PYTHONPATH=. python3 tests/pdf/scanned-image-benchmark.py -v` checks the
generated document with the pinned parser, ensures raster image XObjects and
absence of searchable text, and validates the safe scanner command,
bounded samples, timing math and failure behavior with a mock. CI timing
values are **not actual performance measurements** and are not published as
performance evidence.

This code is not imported by `scan-and-open.py`. It never changes scan
approval, cache, signature freshness, scanner policy, security alerts,
quarantine, chosen browser, other user preferences or file associations.
