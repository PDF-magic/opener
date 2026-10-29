#!/usr/bin/env python3
"""Read-only ClamAV capability diagnostics; never authorizes an opening decision.

This probes the selected clamscan binary's advertised command-line options,
not the installed engine version, active configuration, or successful scanning.
The existing scan-and-open gate remains the sole authority on file opening.
"""

from dataclasses import dataclass
from pathlib import Path
import re
import subprocess
import sys

# Names describe available CLI switches, not enabled protection or engine support.
FEATURE_OPTIONS = (
    ("pdf", "--scan-pdf"),
    ("archives", "--scan-archive"),
    ("ole2", "--scan-ole2"),
    ("html", "--scan-html"),
    ("mail", "--scan-mail"),
    ("pe", "--scan-pe"),
    ("elf", "--scan-elf"),
    ("swf", "--scan-swf"),
)

# Only options actually supplied by scan-and-open.py. The standard '--' end-of-
# options marker is a CLI convention, not an advertised clamscan option.
GATE_OPTIONS = frozenset({
    "--database", "--recursive", "--follow-file-symlinks",
    "--follow-dir-symlinks", "--alert-exceeds-max", "--alert-encrypted",
    "--max-filesize", "--max-scansize", "--max-scantime", "--no-summary",
})

# Inspect option declarations only, not incidental mentions in help descriptions.
# ClamAV formats them as ' --option[=yes/no]' or '-r, --recursive'.
OPTION_LINE = re.compile(r"^\s*(?:-[a-zA-Z0-9],\s*)?(--[a-z][a-z0-9-]*)(?=$|[\s\[=,])")
MAX_HELP_LENGTH = 128 * 1024
HELP_TIMEOUT = 5


@dataclass(frozen=True)
class ScannerFeatureReport:
    """Immutable, path-free report; unavailable probes have *unknown* features."""

    inspected: bool
    supported_features: frozenset[str] = frozenset()
    unsupported_features: frozenset[str] = frozenset()
    supported_gate_options: frozenset[str] = frozenset()
    missing_gate_options: frozenset[str] = frozenset()

    @property
    def advertises_gate_options(self):
        """Diagnostic only; never substitute for a successful actual scan."""
        return self.inspected and not self.missing_gate_options


def inspect_scanner_features(executable):
    """Query only ``clamscan --help``, without scanning files or changing settings.

    Require an explicit absolute binary path from a trusted scanner resolver.
    An unresponsive, missing, malformed or nonzero-status help command yields
    an unknown report, *not* an assertion that features are unsupported.
    """
    if (type(executable) is not str or not executable or "\x00" in executable
            or len(executable) > 4096 or not Path(executable).is_absolute()):
        raise ValueError("An absolute scanner executable path is required.")
    try:
        completed = subprocess.run(
            [executable, "--help"], capture_output=True, text=True,
            timeout=HELP_TIMEOUT, check=False,
        )
    except (OSError, UnicodeError, subprocess.TimeoutExpired):
        return ScannerFeatureReport(inspected=False)
    if (completed.returncode != 0 or not isinstance(completed.stdout, str)
            or not completed.stdout or len(completed.stdout) > MAX_HELP_LENGTH
            or completed.stderr):
        return ScannerFeatureReport(inspected=False)
    options = frozenset(
        match.group(1) for line in completed.stdout.splitlines()
        if (match := OPTION_LINE.match(line))
    )
    # A successful process with no recognizable option declarations is not a
    # trustworthy negative capability result (e.g. a wrapper or wrong binary).
    if not options or "--help" not in options:
        return ScannerFeatureReport(inspected=False)
    supported = frozenset(name for name, flag in FEATURE_OPTIONS if flag in options)
    all_features = frozenset(name for name, _ in FEATURE_OPTIONS)
    return ScannerFeatureReport(
        inspected=True,
        supported_features=supported,
        unsupported_features=all_features - supported,
        supported_gate_options=GATE_OPTIONS & options,
        missing_gate_options=GATE_OPTIONS - options,
    )


def main(args=None):
    """Opt-in, read-only CLI: python3 scanner_feature_check.py /path/clamscan."""
    args = sys.argv[1:] if args is None else args
    if len(args) != 1:
        print("Usage: scanner_feature_check.py /absolute/path/to/clamscan", file=sys.stderr)
        return 2
    try:
        report = inspect_scanner_features(args[0])
    except ValueError:
        print("A valid absolute scanner executable path is required.", file=sys.stderr)
        return 2
    if not report.inspected:
        print("ClamAV feature support: unknown (help probe unavailable)")
        return 1
    for feature, _ in FEATURE_OPTIONS:
        state = "advertised" if feature in report.supported_features else "not advertised"
        print(f"{feature}: {state}")
    if report.missing_gate_options:
        print("Built-in scan options not advertised: " + ", ".join(sorted(report.missing_gate_options)))
        return 1
    print("Built-in scan options: all advertised (actual scan still required)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
