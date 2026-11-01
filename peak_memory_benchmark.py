#!/usr/bin/env python3
"""Opt-in peak RSS measurement of standalone ClamAV on a synthetic PDF.

This diagnostic never reads user documents or produces an opening verdict.
"""
import argparse
import json
import math
import os
from pathlib import Path
import signal
import statistics
import subprocess
import sys
import tempfile
import time

from reference_pdf_collection import REFERENCE_PDFS
from scanner_startup_benchmark import TRUSTED_SCANNERS, command

MIN_SAMPLES = 1
MAX_SAMPLES = 10
TIMEOUT_SECONDS = 180
ERROR = "Peak memory benchmark failed or was incomplete; no results recorded."


def rss_mib(peak, platform=sys.platform):
    """wait4 ru_maxrss is KiB on Linux and bytes on macOS."""
    if (platform not in ("linux", "darwin") or
            type(peak) not in (int, float) or
            not math.isfinite(peak) or peak <= 0):
        raise ValueError(ERROR)
    return peak / (1024 * 1024 if platform == "darwin" else 1024)


def validate(scanner, database, samples):
    if (sys.platform not in ("linux", "darwin") or
            not hasattr(os, "wait4")):
        raise ValueError("Peak process RSS requires Linux or macOS wait4.")
    if (type(scanner) is not str or scanner not in TRUSTED_SCANNERS or
            not Path(scanner).is_file() or not os.access(scanner, os.X_OK)):
        raise ValueError("Choose an installed, trusted clamscan executable.")
    if not isinstance(database, Path) or not database.is_dir():
        raise ValueError("Choose an existing ClamAV signature directory.")
    if type(samples) is not int or not MIN_SAMPLES <= samples <= MAX_SAMPLES:
        raise ValueError("Choose 1 to 10 memory samples.")


def scan_peak_rss_mib(scanner, database, fixture):
    """Reap this exact clamscan child with wait4, not cumulative child usage."""
    process = None
    with tempfile.TemporaryFile(mode="w+t") as output, \
            tempfile.TemporaryFile(mode="w+t") as errors:
        try:
            process = subprocess.Popen(
                command(scanner, database, fixture),
                stdout=output, stderr=errors, start_new_session=True,
            )
            deadline = time.monotonic() + TIMEOUT_SECONDS
            while True:
                try:
                    pid, status, usage = os.wait4(process.pid, os.WNOHANG)
                except InterruptedError:
                    continue
                if pid == process.pid:
                    process.returncode = os.waitstatus_to_exitcode(status)
                    break
                if time.monotonic() >= deadline:
                    raise TimeoutError(ERROR)
                time.sleep(0.02)
            output.seek(0)
            errors.seek(0)
            # An incomplete, warning-bearing, malicious or failed scan must
            # not be presented as a successful memory measurement.
            if (process.returncode != 0 or errors.read(8193).strip() or
                    output.read(8193).strip() != str(fixture) + ": OK"):
                raise RuntimeError(ERROR)
            return rss_mib(usage.ru_maxrss)
        except (OSError, ValueError, TimeoutError):
            raise RuntimeError(ERROR) from None
        finally:
            if process is not None and process.returncode is None:
                # Kill only the detached process group created for this run;
                # do not leave a timed-out scanner running in the background.
                try:
                    os.killpg(process.pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
                try:
                    os.wait4(process.pid, 0)
                except ChildProcessError:
                    pass
                process.returncode = -signal.SIGKILL


def measure(scanner, database, samples=3, *, sampler=scan_peak_rss_mib):
    validate(scanner, database, samples)
    with tempfile.TemporaryDirectory(prefix="pdfmagic-memory-") as folder:
        fixture = Path(folder) / "synthetic.pdf"
        pdf = REFERENCE_PDFS[0].content
        if (not pdf.startswith(b"%PDF-1.4\n") or
                not pdf.endswith(b"%%EOF\n") or len(pdf) >= 4096):
            raise RuntimeError(ERROR)
        fixture.write_bytes(pdf)
        peaks = []
        for index in range(samples + 1):
            try:
                peak = sampler(scanner, database, fixture)
                if type(peak) not in (float, int) or not math.isfinite(peak) or peak <= 0:
                    raise RuntimeError(ERROR)
            except Exception:
                # Never reveal scanner output, file paths or partial samples.
                raise RuntimeError(ERROR) from None
            if index:
                peaks.append(peak)
    return {
        "schemaVersion": 1,
        "scope": "syntheticStandaloneClamavScanPeakRSS",
        "measurement": "directClamscanChildWait4MaxRSS",
        "authorizesOpen": False,
        "fixtureBytes": len(pdf),
        "sampleCount": samples,
        "discardedWarmupRuns": 1,
        "medianPeakRssMiB": round(statistics.median(peaks), 3),
        "maxPeakRssMiB": round(max(peaks), 3),
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--scanner", required=True,
                        help="absolute path to the installed trusted clamscan")
    parser.add_argument("--database", required=True, type=Path,
                        help="existing local signature directory")
    parser.add_argument("--samples", type=int, default=3)
    args = parser.parse_args(argv)
    try:
        result = measure(args.scanner, args.database, args.samples)
    except (ValueError, RuntimeError) as exc:
        parser.exit(1, str(exc) + "\n")
    print(json.dumps(result, sort_keys=True, allow_nan=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
