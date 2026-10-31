#!/usr/bin/env python3
"""opener-0967: confirmed repair must retain a valid ClamAV signature database.

The real Repair Installation.command and actual staged updater are exercised
under a synthetic HOME, but the installer and ClamAV binaries are inert,
checkout-local test substitutes. Never touch installed user signatures.
"""

import os
from pathlib import Path
import pty
import select
import shutil
import signal
import subprocess
import tempfile
import time
import unittest

ROOT = Path(__file__).resolve().parents[2]
INSTALLER = ROOT / "install-allow-and-open.sh"
REPAIR = ROOT / "Repair Installation.command"
UPDATER = ROOT / "update-malware-signatures.sh"
FRESHCLAM_CANDIDATES = (
    "/opt/homebrew/bin/freshclam /usr/local/bin/freshclam "
    "/usr/local/clamav/bin/freshclam"
)
CLAMSCAN_CANDIDATES = (
    "/opt/homebrew/bin/clamscan /usr/local/bin/clamscan "
    "/usr/local/clamav/bin/clamscan"
)

FAKE_FRESHCLAM = """#!/usr/bin/env python3
import os
from pathlib import Path
import sys

stages = [value.split("=", 1)[1] for value in sys.argv[1:]
          if value.startswith("--datadir=")]
if len(stages) != 1:
    raise SystemExit(98)
stage = Path(stages[0])
if not stage.is_dir():
    raise SystemExit(97)
mode = os.environ["FAKE_SIGNATURE_RESULT"]
if mode == "failed":
    (stage / "main.cvd").write_bytes(b"corrupted stage only")
    (stage / "daily.cld").unlink(missing_ok=True)
    raise SystemExit(23)
if mode == "incomplete":
    (stage / "daily.cld").unlink()
elif mode == "replacement":
    (stage / "main.cvd").write_bytes(b"new checked main database")
    (stage / "daily.cld").write_bytes(b"new checked daily database")
elif mode != "unchanged":
    raise SystemExit(96)
"""

FAKE_CLAMSCAN = """#!/usr/bin/env python3
from pathlib import Path
import sys

args = sys.argv[1:]
if (len(args) != 4 or not args[0].startswith("--database=")
        or args[1:3] != ["--no-summary", "--"]):
    raise SystemExit(99)
stage = Path(args[0].split("=", 1)[1])
if not all((stage / name).is_file() and (stage / name).stat().st_size > 0
           for name in ("main.cvd", "daily.cld")):
    raise SystemExit(98)
print(args[3] + ": OK")
"""


class RepairSignatureDatabaseTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.installerSource = INSTALLER.read_text(encoding="utf-8")
        cls.updaterSource = UPDATER.read_text(encoding="utf-8")
        cls.repairSource = REPAIR.read_text(encoding="utf-8")

    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="repair-signatures-")
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.home = self.root / "home"
        self.install = self.home / "Library/Application Support/Studio/allow-and-open"
        self.signatures = self.install / "signatures"
        self.signatures.mkdir(parents=True)
        self.checkout = self.root / "trusted-checkout"
        self.checkout.mkdir()
        repair = self.checkout / REPAIR.name
        shutil.copyfile(REPAIR, repair)
        repair.chmod(0o755)
        self.repair = repair
        scripts = self.checkout / "scripts"
        scripts.mkdir()
        for name in ("report_install_prerequisites.py", "confirm_clamav_install.py"):
            (scripts / name).write_text("# inert repair test fixture\n", encoding="utf-8")

        # Preserve a complete, already-valid main/daily pair and user-defined
        # signatures. Read neither the real HOME nor any installed database.
        (self.signatures / "main.cvd").write_bytes(b"validated main database")
        (self.signatures / "daily.cld").write_bytes(b"validated daily database")
        (self.signatures / "custom.ndb").write_bytes(b"custom retained signatures")
        (self.signatures / "last-successful-update").write_bytes(b"1700000000\n")
        (self.install / "freshclam.conf").write_text(
            'DatabaseDirectory "' + str(self.signatures) + '"\n'
            "DatabaseMirror custom-mirror.invalid\n",
            encoding="utf-8",
        )
        self.signatureNames = (
            "main.cvd", "daily.cld", "custom.ndb", "last-successful-update"
        )

        self.fakeFreshclam = self.root / "fake-freshclam"
        self.fakeClamscan = self.root / "fake-clamscan"
        for path, contents in (
            (self.fakeFreshclam, FAKE_FRESHCLAM),
            (self.fakeClamscan, FAKE_CLAMSCAN),
        ):
            path.write_text(contents, encoding="utf-8")
            path.chmod(0o700)

        # Keep every stage-verification and rollback operation from the
        # production updater. Override ONLY its fixed executable candidates.
        self.assertEqual(self.updaterSource.count(FRESHCLAM_CANDIDATES), 1)
        self.assertEqual(self.updaterSource.count(CLAMSCAN_CANDIDATES), 1)
        updater = self.updaterSource.replace(
            FRESHCLAM_CANDIDATES, str(self.fakeFreshclam)
        ).replace(CLAMSCAN_CANDIDATES, str(self.fakeClamscan))
        (self.checkout / UPDATER.name).write_text(updater, encoding="utf-8")

        # A synthetic installer reproduces the actual installer ordering:
        # create signatures if absent, deploy updater, invoke updater.
        # Never execute the real installer on the CI host.
        fixture = (
            '#!/bin/bash\nset -euo pipefail\n'
            'script_dir="$(cd "$(dirname "$0")" && pwd)"\n'
            'install_dir="$HOME/Library/Application Support/Studio/allow-and-open"\n'
            'mkdir -p "$install_dir/signatures"\n'
            'cp "$script_dir/update-malware-signatures.sh" "$install_dir/"\n'
            'bash "$install_dir/update-malware-signatures.sh"\n'
        )
        (self.checkout / INSTALLER.name).write_text(fixture, encoding="utf-8")

    def snapshot(self):
        return {
            name: (path.read_bytes(), path.stat().st_ino,
                   path.stat().st_mtime_ns, path.stat().st_mode & 0o777)
            for name in self.signatureNames
            for path in [self.signatures / name]
        }

    def noTransientDirectories(self):
        self.assertEqual(list(self.install.glob(".signature-stage.*")), [])
        self.assertEqual(list(self.install.glob(".signature-backup.*")), [])
        self.assertFalse((self.install / ".signature-update-lock").exists())

    def runRepair(self, mode, *, consent="REPAIR"):
        if os.geteuid() == 0:
            self.skipTest("Repair action intentionally refuses root execution")
        child, master = pty.fork()
        if child == 0:
            os.environ["HOME"] = str(self.home)
            os.environ["FAKE_SIGNATURE_RESULT"] = mode
            os.environ["PYTHONDONTWRITEBYTECODE"] = "1"
            os.execv("/bin/bash", ["/bin/bash", str(self.repair)])
        deadline = time.monotonic() + 16
        received = b""
        answered = False
        finished = False
        try:
            while time.monotonic() < deadline:
                ready, _, _ = select.select([master], [], [], 0.1)
                if ready:
                    try:
                        received += os.read(master, 65536)
                    except OSError:  # PTY returns EIO after its slave closes
                        pass
                    if b"Type REPAIR" in received and not answered:
                        os.write(master, (consent + "\n").encode("ascii"))
                        answered = True
                pid, status = os.waitpid(child, os.WNOHANG)
                if pid:
                    finished = True
                    self.assertTrue(answered, "Missing explicit repair confirmation")
                    return os.waitstatus_to_exitcode(status), received.decode(
                        "utf-8", errors="replace"
                    )
            self.fail("Repair exceeded bounded synthetic execution time")
        finally:
            if not finished:
                os.kill(child, signal.SIGKILL)
                os.waitpid(child, 0)
            os.close(master)

    def test_declined_and_unattended_repair_preserve_existing_signatures(self):
        before = self.snapshot()
        originalDir = self.signatures.stat().st_ino
        outcome, _ = self.runRepair("replacement", consent="NO")
        self.assertNotEqual(outcome, 0)
        self.assertEqual(self.snapshot(), before)
        self.assertEqual(self.signatures.stat().st_ino, originalDir)
        result = subprocess.run(
            ["/bin/bash", str(self.repair)],
            input="REPAIR\n", text=True, capture_output=True,
            start_new_session=True, timeout=8,
            env=dict(os.environ, HOME=str(self.home)),
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(self.snapshot(), before)
        self.noTransientDirectories()

    def test_failed_update_during_confirmed_repair_never_discards_database(self):
        before = self.snapshot()
        originalDir = self.signatures.stat().st_ino
        outcome, details = self.runRepair("failed")
        self.assertEqual(outcome, 23, details[-800:])
        self.assertEqual(self.snapshot(), before)
        self.assertEqual(self.signatures.stat().st_ino, originalDir)
        self.assertTrue((self.signatures / "last-attempted-update").is_file())
        self.assertTrue((self.signatures / "last-failed-update").is_file())
        self.noTransientDirectories()

    def test_incomplete_successful_download_cannot_replace_valid_database(self):
        before = self.snapshot()
        originalDir = self.signatures.stat().st_ino
        outcome, details = self.runRepair("incomplete")
        self.assertNotEqual(outcome, 0, details[-800:])
        self.assertEqual(self.snapshot(), before)
        self.assertEqual(self.signatures.stat().st_ino, originalDir)
        self.noTransientDirectories()

    def test_successful_no_change_repair_keeps_complete_database_and_custom_data(self):
        before = self.snapshot()
        outcome, details = self.runRepair("unchanged")
        self.assertEqual(outcome, 0, details[-800:])
        for name in ("main.cvd", "daily.cld", "custom.ndb"):
            self.assertEqual((self.signatures / name).read_bytes(), before[name][0])
        self.assertGreater(
            int((self.signatures / "last-successful-update").read_text()), 1700000000
        )
        self.assertEqual(
            (self.install / "freshclam.conf").read_text(),
            'DatabaseDirectory "' + str(self.signatures)
            + '"\nDatabaseMirror custom-mirror.invalid\n',
        )
        self.noTransientDirectories()

    def test_verified_replacement_keeps_all_mandatory_and_custom_signatures(self):
        outcome, details = self.runRepair("replacement")
        self.assertEqual(outcome, 0, details[-800:])
        self.assertEqual((self.signatures / "main.cvd").read_bytes(),
                         b"new checked main database")
        self.assertEqual((self.signatures / "daily.cld").read_bytes(),
                         b"new checked daily database")
        self.assertEqual((self.signatures / "custom.ndb").read_bytes(),
                         b"custom retained signatures")
        self.noTransientDirectories()

    def test_real_install_and_updater_guards_are_still_required(self):
        self.assertIn('mkdir -p "$install_dir/signatures"', self.installerSource)
        self.assertIn('bash "$install_dir/update-malware-signatures.sh"', self.installerSource)
        self.assertIn('"$script_dir/update-malware-signatures.sh"', self.installerSource)
        self.assertIn('exec /bin/bash "$installer"', self.repairSource)
        self.assertIn('if [ "$response" != "REPAIR" ]; then', self.repairSource)
        self.assertIn('/bin/cp -pR "$signature_dir/." "$stage_dir/"',
                      self.updaterSource)
        self.assertIn('/bin/mv "$signature_dir" "$backup_dir/previous"',
                      self.updaterSource)
        self.assertIn('/bin/mv "$stage_dir" "$signature_dir"', self.updaterSource)
        self.assertIn("# BEGIN staged database verification (opener-0386)",
                      self.updaterSource)
        self.assertNotIn('/bin/rm -rf "$signature_dir"', self.updaterSource)
        ci = (ROOT / ".github/workflows/ci.yml").read_text(encoding="utf-8")
        self.assertIn("tests/signature/repair-preserves-database.py -v", ci)


if __name__ == "__main__":
    unittest.main()
