#!/usr/bin/env python3
"""Keep paired benchmark source comparisons exact across the layout migration."""
from pathlib import Path
import sys

MEDIUM = "medium-pdf-benchmark.py"
FIXTURE = "pdf-parser-memory-benchmark.py"
BOOTSTRAP = (
    b"# Direct CLI and worker execution from a source checkout.\n"
    b"if __name__ == \"__main__\" and not __package__:\n"
    b"    import sys as _benchmark_sys\n"
    b"    from pathlib import Path as _BenchmarkPath\n"
    b"    _benchmark_sys.path.insert(0, str(_BenchmarkPath(__file__).resolve().parents[1]))\n\n"
)
PACKAGE_IMPORT = b"from benchmarks.pdf_parser_memory_benchmark import synthetic_pdf"
LEGACY_IMPORT = b"from pdf_parser_memory_benchmark import synthetic_pdf"


def legacy_medium(source):
    """Reverse only the exact import and direct-CLI layout changes."""
    if source.count(BOOTSTRAP) != 1 or source.count(PACKAGE_IMPORT) != 1:
        raise ValueError("Unexpected legacy benchmark layout translation")
    return source.replace(BOOTSTRAP, b"", 1).replace(PACKAGE_IMPORT, LEGACY_IMPORT, 1)


def compare(baseline, candidate):
    baseline = Path(baseline)
    candidate = Path(candidate) / "benchmarks"
    packaged = (baseline / "benchmarks" / MEDIUM).is_file()
    old_dir = baseline / "benchmarks" if packaged else baseline
    for name in (MEDIUM, FIXTURE):
        old = (old_dir / name).read_bytes()
        new = (candidate / name).read_bytes()
        if not packaged and name == MEDIUM:
            new = legacy_medium(new)
        if old != new:
            raise ValueError(f"Incomparable benchmark source: {name}")
    return f"benchmarks/{MEDIUM}" if packaged else MEDIUM


if __name__ == "__main__":
    if len(sys.argv) != 3:
        raise SystemExit("usage: compare-benchmark-layout.py BASELINE CANDIDATE")
    try:
        print(compare(sys.argv[1], sys.argv[2]))
    except (OSError, ValueError) as error:
        raise SystemExit(str(error))
