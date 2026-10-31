#!/usr/bin/env python3
"""Verify failed-migration rollback and successful cleanup with synthetic apps."""

from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
INSTALLER = ROOT / "install-allow-and-open.sh"


def recovery_handler():
    """Extract the actual EXIT trap; never execute the installer in tests."""
    source = INSTALLER.read_text(encoding="utf-8")
    start = "rollback_installation() {\n"
    stop = "\n}\ntrap rollback_installation EXIT"
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

    def exit_handler(self, *, committed=False, status=0, promoted=False):
        script = (
            "set -euo pipefail\n"
            'installed_app="$1"\n'
            'bundle_stage_dir="$2"\n'
            'legacy_app="$3"\n'
            'script_dir="$4"\n'
            'install_dir="$5"\n'
            'install_snapshot=""\n'
            'snapshot_ready=0\n'
            'legacy_was_moved=0\n'
            f'migration_committed={int(committed)}\n'
            f'new_app_installed={int(promoted)}\n'
            + recovery_handler() + "\n"
            "trap rollback_installation EXIT\n"
            "exit " + str(status) + "\n"
        )
        return subprocess.run(
            ["bash", "-c", script, "cleanup-fixture", str(self.installed),
             str(self.stage), str(self.root / "Applications/Open PDFs in Brave.app"),
             str(ROOT), str(self.root / "programs")],
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
        completed = self.exit_handler(committed=True, promoted=True)
        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertFalse(self.stage.exists())
        self.assertEqual((self.installed / "new-opener").read_bytes(), b"new app")
        self.assertEqual(self.unrelated.read_bytes(), b"preserve me")

    def test_zero_exit_without_completion_restores_working_bundle(self):
        self.add_old()
        self.add_new()
        completed = self.exit_handler(committed=False, promoted=True)
        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertEqual((self.installed / "working-opener").read_bytes(), b"old app")
        self.assertFalse(self.stage.exists())
        self.assertEqual(self.unrelated.read_bytes(), b"preserve me")

    def test_nonzero_exit_restores_working_bundle(self):
        self.add_old()
        self.add_new()
        completed = self.exit_handler(status=19, promoted=True)
        self.assertEqual(completed.returncode, 19, completed.stderr)
        self.assertEqual((self.installed / "working-opener").read_bytes(), b"old app")
        self.assertFalse(self.stage.exists())

    def test_failed_promotion_restores_prior_handler(self):
        self.add_old()
        completed = self.exit_handler(status=23)
        self.assertEqual(completed.returncode, 23)
        self.assertFalse(self.stage.exists())
        self.assertEqual((self.installed / "working-opener").read_bytes(), b"old app")

    def test_symlinked_recovery_bundle_is_never_followed(self):
        self.previous.symlink_to(self.unrelated)
        completed = self.exit_handler(status=17)
        self.assertEqual(completed.returncode, 17)
        self.assertTrue(self.previous.is_symlink())
        self.assertFalse(self.installed.exists())
        self.assertEqual(self.unrelated.read_bytes(), b"preserve me")
        self.assertIn("incomplete", completed.stderr)

    def test_failed_fresh_install_removes_only_scratch_build(self):
        (self.stage / "uncommitted.app").mkdir()
        completed = self.exit_handler(status=29)
        self.assertEqual(completed.returncode, 29)
        self.assertFalse(self.stage.exists())
        self.assertEqual(self.unrelated.read_bytes(), b"preserve me")

    def test_completion_after_all_migration_phases(self):
        source = INSTALLER.read_text(encoding="utf-8")
        self.assertEqual(source.count("migration_committed=1"), 1)
        completion = source.index("migration_committed=1")
        for required in (
            'mv "$app" "$installed_app"',
            'python3 "$script_dir/scripts/reconcile_update_agent.py"',
            'scripts/reconcile_pdf_handler_registration.py',
            'python3 - "$workflow" <<\'PY\'',
            'python3 "$script_dir/offer-restore-pdf-handler.py"',
            'python3 "$install_dir/pdf-handler-status.py"',
            'python3 "$script_dir/scripts/migration_state.py" --home "$HOME" complete "$migration_attempt"',
        ):
            self.assertLess(source.index(required), completion)
        self.assertIn('if [ "$migration_committed" -ne 1 ]', source)
        self.assertIn('trap rollback_installation EXIT', source)
        ci = (ROOT / ".github/workflows/ci.yml").read_text(encoding="utf-8")
        self.assertIn("python3 tests/migration/obsolete-cleanup.py -v", ci)


if __name__ == "__main__":
    unittest.main()
