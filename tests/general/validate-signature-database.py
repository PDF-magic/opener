#!/usr/bin/env python3
"""opener-0386: do not activate downloaded databases until ClamAV loads them."""
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
FRESH_PATHS = "/opt/homebrew/bin/freshclam /usr/local/bin/freshclam /usr/local/clamav/bin/freshclam"
SCAN_PATHS = "/opt/homebrew/bin/clamscan /usr/local/bin/clamscan /usr/local/clamav/bin/clamscan"

FRESH = """#!/bin/bash
set -euo pipefail
stage=""
for arg in "$@"; do
  case "$arg" in --datadir=*) stage="$(printf '%s' "$arg" | cut -c 11-)" ;; esac
done
test -d "$stage" || exit 91
printf 'new main\n' > "$stage/main.cvd"
printf 'new daily\n' > "$stage/daily.cld"
if [ "$FAKE_UPDATE_MODE" = "missing" ]; then /bin/rm "$stage/daily.cld"; fi
if [ "$FAKE_UPDATE_MODE" = "duplicate" ]; then /bin/cp "$stage/main.cvd" "$stage/main.cld"; fi
if [ "$FAKE_UPDATE_MODE" = "link" ]; then
  /bin/rm "$stage/daily.cld"
  /bin/ln -s "$FAKE_OUTSIDE" "$stage/daily.cld"
fi
"""
SCAN = """#!/bin/bash
set -euo pipefail
last=""
for arg in "$@"; do last="$arg"; done
printf '%s\n' "$*" > "$FAKE_SCAN_ARGS"
if [ "$FAKE_SCAN_MODE" = "error" ]; then exit 2; fi
if [ "$FAKE_SCAN_MODE" = "infected" ]; then printf '%s: FOUND\n' "$last"; exit 1; fi
if [ "$FAKE_SCAN_MODE" = "warning" ]; then printf '%s: OK\nWARNING: skipped\n' "$last"; exit 0; fi
if [ "$FAKE_SCAN_MODE" = "false_ok" ]; then printf 'wrong: OK\n'; exit 0; fi
printf '%s: OK\n' "$last"
"""

class SignatureValidationTests(unittest.TestCase):
    def setUp(self):
        folder = tempfile.TemporaryDirectory(prefix="signature-activation-")
        self.addCleanup(folder.cleanup)
        self.root = Path(folder.name)
        self.home = self.root / "home"
        self.install = self.home / "Library/Application Support/Studio/allow-and-open"
        self.live = self.install / "signatures"
        self.live.mkdir(parents=True)
        (self.live / "main.cvd").write_bytes(b"old main\n")
        (self.live / "daily.cld").write_bytes(b"old daily\n")
        (self.live / "custom.ndb").write_bytes(b"custom data\n")
        (self.live / "last-successful-update").write_text("1700000000\n")
        (self.install / "freshclam.conf").write_text("synthetic\n")
        self.original = {p.name: p.read_bytes() for p in self.live.iterdir()}
        self.fresh = self.root / "fake-freshclam"
        self.fresh.write_text(FRESH)
        self.fresh.chmod(0o700)
        self.scanner = self.root / "fake-clamscan"
        self.scanner.write_text(SCAN)
        self.scanner.chmod(0o700)
        original = (ROOT / "update-malware-signatures.sh").read_text()
        self.assertIn(FRESH_PATHS, original)
        self.assertIn(SCAN_PATHS, original)
        self.script = self.root / "update.sh"
        self.script.write_text(original.replace(FRESH_PATHS, str(self.fresh))
                                       .replace(SCAN_PATHS, str(self.scanner)))
        self.outside = self.root / "outside"
        self.outside.write_bytes(b"private")
        self.args = self.root / "scan-args"

    def invoke(self, scan="ok", update="ok", missing_scanner=False):
        if missing_scanner:
            self.scanner.unlink()
        env = dict(os.environ, HOME=str(self.home),
                   FAKE_SCAN_MODE=scan, FAKE_UPDATE_MODE=update,
                   FAKE_OUTSIDE=str(self.outside), FAKE_SCAN_ARGS=str(self.args))
        return subprocess.run(["bash", str(self.script)], env=env,
                              capture_output=True, text=True, timeout=12)

    def assert_preserved(self):
        for name, contents in self.original.items():
            with self.subTest(name=name):
                self.assertEqual((self.live / name).read_bytes(), contents)
        self.assertEqual(list(self.install.glob(".signature-stage.*")), [])
        self.assertEqual(list(self.install.glob(".signature-backup.*")), [])
        self.assertEqual(list(self.install.glob(".signature-validation.*")), [])
        self.assertFalse((self.install / ".signature-update-lock").exists())

    def test_valid_databases_are_scanned_before_promotion(self):
        result = self.invoke()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual((self.live / "main.cvd").read_bytes(), b"new main\n")
        args = self.args.read_text()
        self.assertIn("--database=", args)
        self.assertIn("--no-summary", args)
        self.assertIn(".signature-validation.", args)
        self.assertGreater(int((self.live / "last-successful-update").read_text()), 1700000000)
        self.assertEqual((self.live / "custom.ndb").read_bytes(), b"custom data\n")

    def test_scan_failure_warning_detection_and_wrong_verdict_preserve_previous(self):
        for mode in ("error", "warning", "infected", "false_ok"):
            with self.subTest(mode=mode):
                result = self.invoke(scan=mode)
                self.assertNotEqual(result.returncode, 0)
                self.assertIn("retaining previous database", result.stderr)
                self.assertNotIn(str(self.root), result.stderr)
                self.assert_preserved()

    def test_incomplete_ambiguous_and_symlinked_stage_preserve_previous(self):
        for mode in ("missing", "duplicate", "link"):
            with self.subTest(mode=mode):
                self.assertNotEqual(self.invoke(update=mode).returncode, 0)
                self.assert_preserved()
        self.assertEqual(self.outside.read_bytes(), b"private")

    def test_missing_scanner_blocks_database_promotion(self):
        result = self.invoke(missing_scanner=True)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("scanner is unavailable", result.stderr)
        self.assert_preserved()

    def test_ci_and_updater_ordering(self):
        script = (ROOT / "update-malware-signatures.sh").read_text()
        ci = (ROOT / ".github/workflows/ci.yml").read_text()
        self.assertIn("python3 tests/general/validate-signature-database.py -v", ci)
        self.assertLess(script.index("if ! scan_output="), script.index("success_tmp="))
        self.assertLess(script.index("success_tmp="), script.index('backup_dir="$(/usr/bin/mktemp'))
        self.assertIn('if [ -n "$validation_probe" ]', script)

if __name__ == "__main__":
    unittest.main()
