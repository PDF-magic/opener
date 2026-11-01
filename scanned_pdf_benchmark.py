#!/usr/bin/env python3
"""Opt-in ClamAV benchmark of a synthetic, raster-only scanned PDF.

This is scan-process latency, not full app opening, and never an open verdict.
No user PDFs, OCR, network, settings, or production scan controls are touched.
"""

import argparse
import json
import math
from pathlib import Path
import statistics
import subprocess
import tempfile
import time
import zlib

from scanner_startup_benchmark import (
    DEFAULT_DATABASE, TRUSTED_SCANNERS, command,
)

WIDTH = 1275  # US Letter at 150 dpi
HEIGHT = 1650
MIN_PAGES = 1
MAX_PAGES = 4
MIN_RUNS = 3
MAX_RUNS = 7
TIMEOUT_SECONDS = 180
ERROR = "Scanned-PDF benchmark unavailable or incomplete; no results recorded."


def _image(page_index):
    """Raster-only monochrome-looking grayscale page, with no document text."""
    pixels = bytearray(b"\xff" * (WIDTH * HEIGHT))
    for row in range(105, HEIGHT - 110, 36):
        stop = WIDTH - 100 - ((row // 36 + page_index) % 6) * 55
        for col in range(100, stop, 3):
            if ((col // 15 + row // 36 + page_index) % 9) != 0:
                pos = row * WIDTH + col
                pixels[pos:pos + 2] = b"\x32\x58"
    return zlib.compress(pixels, level=6)


def scanned_pdf(pages=2):
    """Build a reproducible PDF with one full-page image XObject per page."""
    if type(pages) is not int or not MIN_PAGES <= pages <= MAX_PAGES:
        raise ValueError("Page count must be between 1 and 4")
    children = b" ".join(f"{3 + 3 * i} 0 R".encode("ascii")
                         for i in range(pages))
    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Count " + str(pages).encode("ascii")
        + b" /Kids [" + children + b"] >>",
    ]
    for index in range(pages):
        page = 3 + 3 * index
        drawing = b"q\n612 0 0 792 0 0 cm\n/Scan Do\nQ\n"
        compressed = _image(index)
        objects.extend([
            (b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] "
             b"/Resources << /XObject << /Scan " +
             str(page + 2).encode("ascii") +
             b" 0 R >> >> /Contents " + str(page + 1).encode("ascii") +
             b" 0 R >>"),
            b"<< /Length " + str(len(drawing)).encode("ascii") +
            b" >>\nstream\n" + drawing + b"endstream",
            (b"<< /Type /XObject /Subtype /Image /Width " +
             str(WIDTH).encode("ascii") + b" /Height " +
             str(HEIGHT).encode("ascii") +
             b" /ColorSpace /DeviceGray /BitsPerComponent 8 "
             b"/Filter /FlateDecode /Length " +
             str(len(compressed)).encode("ascii") +
             b" >>\nstream\n" + compressed + b"\nendstream"),
        ])
    data = bytearray(b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n")
    offsets = [0]
    for number, contents in enumerate(objects, 1):
        offsets.append(len(data))
        data.extend(f"{number} 0 obj\n".encode("ascii"))
        data.extend(contents)
        data.extend(b"\nendobj\n")
    xref_start = len(data)
    data.extend(f"xref\n0 {len(offsets)}\n0000000000 65535 f \n".encode("ascii"))
    for offset in offsets[1:]:
        data.extend(f"{offset:010d} 00000 n \n".encode("ascii"))
    data.extend(
        f"trailer\n<< /Size {len(offsets)} /Root 1 0 R >>\n"
        f"startxref\n{xref_start}\n%%EOF\n".encode("ascii")
    )
    return bytes(data)


def validate(scanner, database, pages, runs):
    if (type(scanner) is not str or scanner not in TRUSTED_SCANNERS or
            not Path(scanner).is_file() or not Path(scanner).stat().st_mode & 0o111):
        raise ValueError("Choose an installed, trusted clamscan executable")
    if not isinstance(database, Path) or not database.is_dir():
        raise ValueError("The installed ClamAV signatures are unavailable")
    if type(pages) is not int or not MIN_PAGES <= pages <= MAX_PAGES:
        raise ValueError("Page count must be between 1 and 4")
    if type(runs) is not int or not MIN_RUNS <= runs <= MAX_RUNS:
        raise ValueError("Use 3 to 7 measured runs")


def timed_scan(scanner, database, path, *, runner, clock):
    started = clock()
    try:
        outcome = runner(command(scanner, database, path), capture_output=True,
                         text=True, timeout=TIMEOUT_SECONDS, check=False)
    except (OSError, subprocess.SubprocessError) as exc:
        raise RuntimeError(ERROR) from exc
    elapsed = clock() - started
    if (outcome.returncode != 0 or type(outcome.stdout) is not str or
            outcome.stdout.strip() != f"{path}: OK" or
            type(outcome.stderr) is not str or outcome.stderr.strip() or
            not math.isfinite(elapsed) or elapsed <= 0):
        raise RuntimeError(ERROR)
    return elapsed


def measure(scanner, database, pages=2, runs=5, *,
            runner=subprocess.run, clock=time.perf_counter):
    """Return metrics only after a successful warmup and every measured scan."""
    validate(scanner, database, pages, runs)
    payload = scanned_pdf(pages)
    with tempfile.TemporaryDirectory(prefix="scanned-pdf-benchmark-") as folder:
        path = Path(folder) / "synthetic-raster.pdf"
        path.write_bytes(payload)
        timed_scan(scanner, database, path, runner=runner, clock=clock)
        elapsed = [timed_scan(scanner, database, path, runner=runner, clock=clock)
                   for _ in range(runs)]
    ordered = sorted(elapsed)
    return {
        "schemaVersion": 1,
        "scope": "syntheticScannedPdfClamscanLatency",
        "authorizesOpen": False,
        "pages": pages,
        "dpi": 150,
        "rasterPixelsPerPage": WIDTH * HEIGHT,
        "fixtureBytes": len(payload),
        "warmupRuns": 1,
        "sampleCount": runs,
        "medianScanMs": round(statistics.median(ordered) * 1000, 3),
        "p90ScanMs": round(ordered[math.ceil(0.9 * runs) - 1] * 1000, 3),
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--scanner", required=True,
                        help="absolute installed trusted clamscan path")
    parser.add_argument("--database", type=Path, default=DEFAULT_DATABASE,
                        help="existing ClamAV signature directory")
    parser.add_argument("--pages", type=int, default=2)
    parser.add_argument("--runs", type=int, default=5)
    args = parser.parse_args(argv)
    try:
        report = measure(args.scanner, args.database, args.pages, args.runs)
    except (ValueError, RuntimeError) as exc:
        parser.exit(1, str(exc) + "\n")
    print(json.dumps(report, sort_keys=True, allow_nan=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
