#!/usr/bin/env python3
"""opener-0388: detect unfinished FreshClam downloads without claiming success."""
import os
from pathlib import Path
import subprocess
import tempfile
import time
import unittest

ROOT = Path(__file__).resolve().parents[2]
CANDIDATES = "/opt/homebrew/bin/freshclam /usr/local/bin/freshclam /usr/local/clamav/bin/freshclam"
FAKE = """#!/bin/bash
set -euo pipefail
# The installed wrapper now directs FreshClam to a disposable stage.
# Write fixtures to that stage, not to the protected live database.
for argument in "$@"; do
  case "$argument" in --datadir=*) FAKE_DATA="${argument#--datadir=}" ;; esac
done
case "$FAKE_MODE" in
  temp) printf partial > "$FAKE_DATA/daily.cvd.tmp" ;;
  hidden) printf partial > "$FAKE_DATA/.main.cld.part" ;;
  download) printf partial > "$FAKE_DATA/main.cvd.download" ;;
  delta) printf partial > "$FAKE_DATA/daily.cdiff" ;;
  zero) : > "$FAKE_DATA/main.cvd" ;;
  truncated) printf 'ClamAV-VDB:build:123:' > "$FAKE_DATA/daily.cld" ;;
  complete) { printf 'ClamAV-VDB:build:123:'; printf '%0492d' 0; } > "$FAKE_DATA/main.cvd" ;;
  symlink) ln -s "$FAKE_PRIVATE" "$FAKE_DATA/main.cvd" ;;
  clean) : ;;
esac
exit "$FAKE_EXIT"
"""


class IncompleteDownloadTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory(prefix="incomplete-clamav-download-")
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        self.home = self.root / "home"
        self.stamps = self.home / "Library/Application Support/Studio/allow-and-open/signatures"
        self.stamps.mkdir(parents=True)
        self.success = self.stamps / "last-successful-update"
        self.success.write_text("1700000000\n")
        self.private = self.root / "outside"
        self.private.write_text("not a database")
        self.fake = self.root / "fake-freshclam"
        self.fake.write_text(FAKE)
        self.fake.chmod(0o700)
        original = (ROOT / "update-malware-signatures.sh").read_text()
        self.assertIn(CANDIDATES, original)
        self.script = self.root / "updater.sh"
        # Synthetic update tests bypass only the separately tested ClamAV
        # stage-load probe in their disposable updater copy.
        first = original.index("# BEGIN staged database verification (opener-0386)")
        last = original.index("# END staged database verification (opener-0386)") + len("# END staged database verification (opener-0386)")
        original = original[:first] + original[last:]
        self.script.write_text(original.replace(CANDIDATES, str(self.fake)))

    def invoke(self, mode="clean", exit_code=0):
        env = dict(os.environ, HOME=str(self.home), FAKE_MODE=mode,
                   FAKE_EXIT=str(exit_code), FAKE_DATA=str(self.stamps),
                   FAKE_PRIVATE=str(self.private))
        return subprocess.run(["bash", str(self.script)], env=env,
                              text=True, capture_output=True, timeout=12)

    def assert_incomplete(self, result):
        self.assertNotEqual(result.returncode, 0, result.stderr)
        self.assertIn("signature download is incomplete", result.stderr)
        self.assertEqual(self.success.read_text(), "1700000000\n")
        self.assertTrue((self.stamps / "last-attempted-update").is_file())
        failure = (self.stamps / "last-failed-update").read_text().strip().split()
        self.assertEqual(len(failure), 2)
        self.assertEqual(failure[1], "incomplete-download")
        self.assertLessEqual(abs(time.time() - int(failure[0])), 10)
        self.assertNotIn(str(self.home), (self.stamps / "last-failed-update").read_text())

    def test_zero_exit_with_partial_transfer_artifacts_fails_closed(self):
        for mode in ("temp", "hidden", "download", "delta"):
            with self.subTest(mode=mode):
                for candidate in self.stamps.iterdir():
                    if candidate.name != "last-successful-update":
                        candidate.unlink()
                self.assert_incomplete(self.invoke(mode))

    def test_empty_database_never_advances_success(self):
        self.assert_incomplete(self.invoke("zero"))

    def test_truncated_recognizable_header_never_advances_success(self):
        self.assert_incomplete(self.invoke("truncated"))

    def test_symlink_database_is_rejected_without_following(self):
        self.assert_incomplete(self.invoke("symlink"))
        self.assertEqual(self.private.read_text(), "not a database")

    def test_clean_success_keeps_existing_update_semantics(self):
        result = self.invoke("clean")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertGreater(int(self.success.read_text()), 1700000000)
        self.assertFalse((self.stamps / "last-failed-update").exists())

    def test_complete_header_is_not_mistaken_for_partial(self):
        result = self.invoke("complete")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertGreater((self.stamps / "main.cvd").stat().st_size, 511)

    def test_freshclam_nonzero_remains_distinct_failure(self):
        result = self.invoke("temp", exit_code=17)
        self.assertEqual(result.returncode, 17)
        self.assertEqual(self.success.read_text(), "1700000000\n")
        failure = (self.stamps / "last-failed-update").read_text()
        self.assertIn("freshclam-error", failure)
        self.assertNotIn("incomplete-download", failure)

    def test_installed_scan_gate_and_agent_not_weakened(self):
        scanner = (ROOT / "scan-and-open.py").read_text()
        self.assertIn("MAX_DATABASE_AGE = 48 * 60 * 60", scanner)
        self.assertNotIn("check_incomplete_downloads", scanner)
        installer = (ROOT / "install-allow-and-open.sh").read_text()
        self.assertIn("'StartInterval': 14400", installer)
        self.assertIn("'RunAtLoad': True", installer)
        source = (ROOT / "update-malware-signatures.sh").read_text()
        self.assertLess(source.index('check_incomplete_downloads "$stage_dir"'),
                        source.index('last-successful-update'))
        self.assertIn('failure_reason="incomplete-download"', source)
        self.assertIn("trap cleanup EXIT", source)
        self.assertIn("cleanup_progress", source)
        ci = (ROOT / ".github/workflows/ci.yml").read_text()
        self.assertIn("python3 tests/general/incomplete-signature-downloads.py -v", ci)


if __name__ == "__main__":
    unittest.main()
