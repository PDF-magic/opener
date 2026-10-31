#!/usr/bin/env python3
"""Exercise the real installer EXIT handler with synthetic application bundles."""

from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
INSTALLER = ROOT / "install-allow-and-open.sh"


def cleanup_handler():
    """Extract the actual trap without running any installation commands."""
    source = INSTALLER.read_text(encoding="utf-8")
    start = "cleanup_bundle_stage() {\n"
    stop = "\n}\ntrap cleanup_bundle_stage EXIT"
    assert source.count(start) == 1 and source.count(stop) == 1
    return start + source.split(start, 1)[1].split(stop, 1)[0] + "\n}"


class MigrationCleanupTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory(prefix="opener-cleanup-")
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        self.installed = self.root / "Applications/PDF Magic Opener.app"
        self.stage = self.root / "Applications/.pdf-magic-opener-build.synthetic"
        self.stage.mkdir(parents=True)
        self.previous = self.stage / "previous.app"
        self.unrelated = self.root / "user-customizations"
        self.unrelated.write_bytes(b"preserve me")

    def exit_handler(self, *, complete, status):
        program = (
            "set -euo pipefail\n"
            'installed_app="$1"\n'
            'bundle_stage_dir="$2"\n'
            'migration_complete="$3"\n'
            + cleanup_handler() + "\n"
            "trap cleanup_bundle_stage EXIT\n"
            "exit " + str(status) + "\n"
        )
        return subprocess.run(
            ["bash", "-c", program, "cleanup-fixture", str(self.installed),
             str(self.stage), str(int(complete))],
            capture_output=True, text=True, check=False, timeout=5,
        )

    def add_old(self):
        self.previous.mkdir()
        (self.previous / "working-opener").write_bytes(b"old app")

    def add_new(self):
        self.installed.mkdir()
        (self.installed / "new-opener").write_bytes(b"new app")

    def test_success_removes_obsolete_previous_bundle(self):
        self.add_old()
        self.add_new()
        completed = self.exit_handler(complete=True, status=0)
        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertFalse(self.stage.exists())
        self.assertEqual((self.installed / "new-opener").read_bytes(), b"new app")
        self.assertEqual(self.unrelated.read_bytes(), b"preserve me")

    def test_zero_exit_without_completion_keeps_previous_bundle(self):
        self.add_old()
        self.add_new()
        result = self.exit_handler(complete=False, status=0)
        self.assertEqual(result.returncode, 0)
        self.assertEqual((self.previous / "working-opener").read_bytes(), b"old app")
        self.assertTrue((self.installed / "new-opener").is_file())
        self.assertIn("retained in staging", result.stderr)

    def test_nonzero_exit_never_disposes_previous_bundle(self):
        self.add_old()
        self.add_new()
        result = self.exit_handler(complete=True, status=19)
        self.assertEqual(result.returncode, 19)
        self.assertEqual((self.previous / "working-opener").read_bytes(), b"old app")

    def test_failed_promotion_restores_prior_handler(self):
        self.add_old()
        result = self.exit_handler(complete=False, status=23)
        self.assertEqual(result.returncode, 23)
        self.assertFalse(self.stage.exists())
        self.assertEqual((self.installed / "working-opener").read_bytes(), b"old app")

    def test_symlinked_recovery_bundle_is_never_followed(self):
        self.previous.symlink_to(self.unrelated)
        result = self.exit_handler(complete=False, status=17)
        self.assertEqual(result.returncode, 17)
        self.assertTrue(self.previous.is_symlink())
        self.assertFalse(self.installed.exists())
        self.assertEqual(self.unrelated.read_bytes(), b"preserve me")

    def test_failed_fresh_install_removes_only_scratch_build(self):
        (self.stage / "uncommitted.app").mkdir()
        result = self.exit_handler(complete=False, status=29)
        self.assertEqual(result.returncode, 29)
        self.assertFalse(self.stage.exists())
        self.assertEqual(self.unrelated.read_bytes(), b"preserve me")

    def test_completion_is_after_all_migration_phases(self):
        source = INSTALLER.read_text(encoding="utf-8")
        self.assertEqual(source.count("migration_complete=1"), 1)
        completion = source.index("migration_complete=1")
        for required in (
            'mv "$app" "$installed_app"',
            'launchctl bootstrap "gui/$UID" "$agent"',
            'python3 - "$workflow" <<\'PY\'',
            'python3 "$script_dir/offer-restore-pdf-handler.py"',
            'python3 "$install_dir/pdf-handler-status.py"',
            'python3 "$script_dir/scripts/migration_state.py" --home "$HOME" complete "$migration_attempt"',
        ):
            self.assertLess(source.index(required), completion)
        self.assertIn('if [ "$status" -eq 0 ] && [ "$migration_complete" -eq 1 ]',
                      source)
        ci = (ROOT / ".github/workflows/ci.yml").read_text(encoding="utf-8")
        self.assertIn("python3 tests/migration/obsolete-cleanup.py -v", ci)


if __name__ == "__main__":
    unittest.main()
