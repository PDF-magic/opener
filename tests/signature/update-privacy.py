#!/usr/bin/env python3
"""opener-0396: PDF bytes and paths must not enter signature-update traffic."""
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parent
UPDATER_CANDIDATES = "/opt/homebrew/bin/freshclam /usr/local/bin/freshclam /usr/local/clamav/bin/freshclam"
FAKE_FRESHCLAM = """#!/bin/bash
set -euo pipefail
printf '%s\\n' "$@" > "$OBSERVED_ARGS"
cat > "$OBSERVED_STDIN"
stage=""
for argument in "$@"; do
  case "$argument" in --datadir=*) stage="$(printf '%s' "$argument" | sed 's/^--datadir=//')" ;; esac
done
[ -n "$stage" ] && [ -d "$stage" ] || exit 93
printf 'new main signatures\\n' > "$stage/main.cvd"
printf 'new daily signatures\\n' > "$stage/daily.cld"
"""


class SignatureUpdatePrivacyTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="signature-update-privacy-")
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.home = self.root / "home"
        self.install = self.home / "Library/Application Support/Studio/allow-and-open"
        self.signatures = self.install / "signatures"
        self.signatures.mkdir(parents=True)
        (self.signatures / "main.cvd").write_bytes(b"original main signatures\n")
        (self.signatures / "daily.cld").write_bytes(b"original daily signatures\n")
        (self.signatures / "custom.ndb").write_bytes(b"custom signatures\n")
        self.config = self.install / "freshclam.conf"
        self.config.write_text('DatabaseDirectory "' + str(self.signatures) + '"\n'
                               'DatabaseMirror database.clamav.net\n')
        self.original_config = self.config.read_bytes()
        self.document = self.root / "scanned files" / "private.pdf"
        self.document.parent.mkdir()
        self.canary = "%PDF-1.7\nCONFIDENTIAL-SCAN-CANARY-0396\n%%EOF\n"
        self.document.write_text(self.canary)
        self.args_log = self.root / "freshclam-args"
        self.stdin_log = self.root / "freshclam-stdin"
        self.fake = self.root / "fake-freshclam"
        self.fake.write_text(FAKE_FRESHCLAM)
        self.fake.chmod(0o700)

        script = (ROOT / "update-malware-signatures.sh").read_text()
        self.assertIn(UPDATER_CANDIDATES, script)
        # Bypass only the independently tested database-load probe in this copy.
        begin = script.index("# BEGIN staged database verification (opener-0386)")
        end = script.index("# END staged database verification (opener-0386)")
        end += len("# END staged database verification (opener-0386)")
        script = script[:begin] + script[end:]
        self.script = self.root / "update.sh"
        self.script.write_text(script.replace(UPDATER_CANDIDATES, str(self.fake)))

    def invoke(self, *arguments, input_text=None):
        env = dict(os.environ, HOME=str(self.home),
                   OBSERVED_ARGS=str(self.args_log), OBSERVED_STDIN=str(self.stdin_log))
        return subprocess.run(["bash", str(self.script), *map(str, arguments)],
                              input=input_text, text=True, capture_output=True,
                              env=env, timeout=15)

    def test_piped_document_bytes_never_reach_freshclam_stdin_or_arguments(self):
        result = self.invoke(input_text=self.canary)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.stdin_log.read_bytes(), b"")
        arguments = self.args_log.read_text().splitlines()
        self.assertEqual(len(arguments), 2, arguments)
        self.assertEqual(arguments[0], "--config-file=" + str(self.config))
        self.assertTrue(arguments[1].startswith("--datadir=" + str(self.install / ".signature-stage.")))
        self.assertNotIn(str(self.document), " ".join(arguments))
        self.assertNotIn("CONFIDENTIAL-SCAN-CANARY-0396", " ".join(arguments))
        self.assertEqual(self.document.read_text(), self.canary)
        self.assertEqual(self.config.read_bytes(), self.original_config)
        self.assertEqual((self.signatures / "custom.ndb").read_bytes(), b"custom signatures\n")

    def test_document_path_argument_rejected_before_network_updater_starts(self):
        result = self.invoke(self.document)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("do not accept document arguments", result.stderr)
        self.assertNotIn(str(self.document), result.stderr)
        self.assertFalse(self.args_log.exists())
        self.assertFalse(self.stdin_log.exists())
        self.assertFalse((self.signatures / "last-attempted-update").exists())
        self.assertEqual(self.config.read_bytes(), self.original_config)
        self.assertEqual((self.signatures / "main.cvd").read_bytes(), b"original main signatures\n")

    def test_manual_update_ui_uses_fixed_dns_lookup_and_zero_document_arguments(self):
        view = (ROOT / "PDFMagicOpenerApp/UpdatesSettingsView.swift").read_text()
        self.assertIn('process.arguments = ["+short", "+time=3", "+tries=1", "TXT", "current.cvd.clamav.net"]', view)
        self.assertIn("process.arguments = [script.path]", view)
        self.assertIn("process.standardOutput = FileHandle.nullDevice", view)
        self.assertIn("process.standardError = FileHandle.nullDevice", view)
        self.assertNotIn("URLSession", view)

    def test_ci_covers_privacy_without_changing_local_scan_gate(self):
        script = (ROOT / "update-malware-signatures.sh").read_text()
        self.assertIn('"$updater" --config-file="$install_dir/freshclam.conf" --datadir="$stage_dir" </dev/null &', script)
        self.assertIn('if [ "$#" -ne 0 ]; then', script)
        ci = (ROOT / ".github/workflows/ci.yml").read_text()
        self.assertIn("python3 test-signature-update-privacy.py -v", ci)
        scanner = (ROOT / "scan-and-open.py").read_text()
        self.assertIn("MAX_DATABASE_AGE = 48 * 60 * 60", scanner)
        self.assertIn("check_database()", scanner)


if __name__ == "__main__":
    unittest.main()
