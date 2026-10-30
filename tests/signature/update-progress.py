#!/usr/bin/env python3
"""opener-0383: real FreshClam lifetime markers, without synthetic percentages."""
import os
from pathlib import Path
import re
import subprocess
import tempfile
import time
import unittest

ROOT = Path(__file__).resolve().parents[2]
SCANNER_PATHS = "/opt/homebrew/bin/freshclam /usr/local/bin/freshclam /usr/local/clamav/bin/freshclam"


class SignatureUpdateProgressTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory(prefix="signature-progress-")
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        self.home = self.root / "home"
        self.signatures = (self.home / "Library/Application Support/Studio/allow-and-open/signatures")
        self.signatures.mkdir(parents=True)
        self.fake = self.root / "fake-freshclam"
        self.fake.write_text(
            "#!/bin/bash\n"
            'while [ ! -f "$FAKE_RELEASE" ]; do sleep 0.05; done\n'
            'exit "$FAKE_EXIT"\n'
        )
        self.fake.chmod(0o700)
        original = (ROOT / "update-malware-signatures.sh").read_text()
        self.assertIn(SCANNER_PATHS, original)
        self.script = self.root / "test-update.sh"
        # Synthetic update tests bypass only the separately tested ClamAV
        # stage-load probe in their disposable updater copy.
        first = original.index("# BEGIN staged database verification (opener-0386)")
        last = original.index("# END staged database verification (opener-0386)") + len("# END staged database verification (opener-0386)")
        original = original[:first] + original[last:]
        self.script.write_text(original.replace(SCANNER_PATHS, str(self.fake)))
        self.marker = self.signatures / "update-in-progress"
        self.processes = []
        self.addCleanup(self.cleanup_processes)

    def cleanup_processes(self):
        for process in self.processes:
            if process.poll() is None:
                process.kill()
            process.communicate(timeout=5)

    def start_update(self, release, exit_code=0):
        environment = dict(os.environ, HOME=str(self.home),
                           FAKE_RELEASE=str(release), FAKE_EXIT=str(exit_code))
        process = subprocess.Popen(["bash", str(self.script)], env=environment,
                                   stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        self.processes.append(process)
        deadline = time.monotonic() + 8
        while time.monotonic() < deadline:
            if self.marker.exists() and self.current_pid() == process.pid:
                return process
            if process.poll() is not None:
                out, err = process.communicate()
                self.fail(f"Updater ended without a running marker: {out} {err}")
            time.sleep(0.05)
        self.fail("Updater failed to record its live progress marker")

    def current_pid(self):
        try:
            raw = self.marker.read_text()
        except FileNotFoundError:
            return None
        match = re.fullmatch(r"[0-9]{1,12} ([1-9][0-9]{0,9})\n", raw)
        self.assertIsNotNone(match, "Unexpected progress record format")
        self.assertLessEqual(self.marker.stat().st_size, 48)
        return int(match.group(1))

    def finish(self, process, release, expected=0):
        release.touch()
        out, err = process.communicate(timeout=10)
        self.assertEqual(process.returncode, expected, (out, err))

    def test_live_update_starts_only_with_freshclam_and_clears_after_success(self):
        release = self.root / "release-success"
        process = self.start_update(release)
        self.assertEqual(self.current_pid(), process.pid)
        self.assertIsNotNone((self.signatures / "last-attempted-update").read_text())
        self.assertFalse((self.signatures / "last-successful-update").exists())
        self.finish(process, release)
        self.assertFalse(self.marker.exists())
        self.assertTrue((self.signatures / "last-successful-update").exists())

    def test_failed_updater_clears_progress_without_advancing_success(self):
        previous = self.signatures / "last-successful-update"
        previous.write_text("1700000000\n")
        release = self.root / "release-failure"
        process = self.start_update(release, exit_code=23)
        self.finish(process, release, expected=23)
        self.assertFalse(self.marker.exists())
        self.assertEqual(previous.read_text(), "1700000000\n")

    def test_concurrent_updater_cannot_overwrite_active_progress(self):
        release = self.root / "release-first"
        first = self.start_update(release)
        second = subprocess.run(
            ["bash", str(self.script)],
            env=dict(os.environ, HOME=str(self.home), FAKE_EXIT="0"),
            capture_output=True, text=True, timeout=10,
        )
        self.assertNotEqual(second.returncode, 0)
        self.assertEqual(self.current_pid(), first.pid)
        self.finish(first, release)
        self.assertFalse(self.marker.exists())

    def test_missing_updater_never_advertises_progress_or_success(self):
        self.fake.unlink()
        result = subprocess.run(["bash", str(self.script)],
                                env=dict(os.environ, HOME=str(self.home)),
                                capture_output=True, text=True, timeout=10)
        self.assertNotEqual(result.returncode, 0)
        self.assertFalse(self.marker.exists())
        self.assertFalse((self.signatures / "last-successful-update").exists())
        self.assertTrue((self.signatures / "last-attempted-update").exists())

    def test_updates_page_and_native_reader_are_read_only(self):
        view = (ROOT / "PDFMagicOpenerApp/UpdatesSettingsView.swift").read_text()
        reader = (ROOT / "PDFMagicOpenerApp/SignatureUpdateProgress.swift").read_text()
        project = (ROOT / "PDFMagicOpener.xcodeproj/project.pbxproj").read_text()
        ci = (ROOT / ".github/workflows/ci.yml").read_text()
        self.assertIn("SignatureUpdateProgress.readInstalled(now: timeline.date)", view)
        self.assertIn("TimelineView(.periodic(from: .now, by: 2))", view)
        self.assertIn('accessibilityIdentifier("signatureUpdateProgress")', view)
        self.assertIn("ProgressView()", view)
        self.assertNotIn("ProgressView(value:", view)
        for required in ("O_NOFOLLOW", "O_NONBLOCK", "fstat(", "S_IFREG",
                         "kill(pid, 0)", "metadata.st_size <= 48"):
            self.assertIn(required, reader)
        for forbidden in ("URLSession", "Process(", "UserDefaults",
                          "write(to:", "removeItem(", "downloadTask"):
            self.assertNotIn(forbidden, reader)
        self.assertEqual(project.count("path = SignatureUpdateProgress.swift;"), 1)
        self.assertIn("test-signature-update-progress.swift", ci)
        self.assertIn("python3 tests/signature/update-progress.py -v", ci)

    def test_active_marker_is_only_display_metadata(self):
        script = (ROOT / "update-malware-signatures.sh").read_text()
        self.assertIn('progress_record="$(/bin/date +%s) $$"', script)
        self.assertIn('trap cleanup EXIT', script)
        self.assertIn('cleanup_progress', script)
        self.assertIn('"$updater" --config-file=', script)
        self.assertIn("last-successful-update", script)
        scan = (ROOT / "scan-and-open.py").read_text()
        self.assertNotIn("update-in-progress", scan)
        self.assertIn("MAX_DATABASE_AGE = 48 * 60 * 60", scan)


if __name__ == "__main__":
    unittest.main()
