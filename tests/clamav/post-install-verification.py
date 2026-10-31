#!/usr/bin/env python3
"""Hermetic post-install ClamAV dependency verification regressions (opener-0963)."""

from contextlib import redirect_stderr, redirect_stdout
import importlib.util
import io
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.dont_write_bytecode = True
spec = importlib.util.spec_from_file_location(
    "post_install", ROOT / "scripts/verify_installed_clamav.py"
)
helper = importlib.util.module_from_spec(spec)
spec.loader.exec_module(helper)


class PostInstallClamAVTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        root = Path(temporary.name)
        self.candidates = tuple(
            str(root / prefix / "clamscan") for prefix in ("arm", "intel", "standalone")
        )

    def make_executable(self, path, executable=True):
        candidate = Path(path)
        candidate.parent.mkdir(parents=True, exist_ok=True)
        candidate.write_bytes(b"#!/bin/sh\nexit 0\n")
        candidate.chmod(0o755 if executable else 0o644)
        return candidate

    def make_pair(self, index=0, updater=True):
        scanner = self.make_executable(self.candidates[index])
        if updater:
            self.make_executable(scanner.with_name("freshclam"))
        return str(scanner)

    @staticmethod
    def version_probe(command, *, text, timeout, stderr):
        assert len(command) == 2 and command[1] == "--version"
        assert text is True and timeout == 5 and stderr == subprocess.DEVNULL
        return "ClamAV 1.4.3/28760/Thu Oct 31"

    def verify(self, probe=None):
        return helper.verify_installed_dependencies(
            candidates=self.candidates, probe=probe or self.version_probe
        )

    def test_matching_scanner_and_updater_are_verified_without_mutation(self):
        scanner = self.make_pair()
        before = [
            (p.read_bytes(), p.stat().st_mtime_ns)
            for p in (Path(scanner), Path(scanner).with_name("freshclam"))
        ]
        self.assertEqual(self.verify(), ("1.4.3", "1.4.3"))
        after = [
            (p.read_bytes(), p.stat().st_mtime_ns)
            for p in (Path(scanner), Path(scanner).with_name("freshclam"))
        ]
        self.assertEqual(before, after)

    def test_missing_scanner_fails_before_version_probe(self):
        with self.assertRaisesRegex(helper.DependencyVerificationError, "scanner is missing"):
            self.verify(probe=lambda *_a, **_k: self.fail("Do not execute a command"))

    def test_missing_or_nonexecutable_freshclam_is_refused(self):
        scanner = self.make_pair(updater=False)
        for state in ("missing", "non-executable"):
            with self.subTest(state=state):
                if state == "non-executable":
                    self.make_executable(Path(scanner).with_name("freshclam"), False)
                with self.assertRaisesRegex(helper.DependencyVerificationError, "freshclam"):
                    self.verify(probe=lambda *_a, **_k: self.fail("No probe should run"))

    def test_rejects_directory_and_broken_symlinks(self):
        Path(self.candidates[0]).mkdir(parents=True)
        Path(self.candidates[1]).parent.mkdir(parents=True)
        Path(self.candidates[1]).symlink_to(Path(self.candidates[1]).with_name("missing"))
        with self.assertRaises(helper.DependencyVerificationError):
            self.verify()
        self.make_pair(2)
        self.assertEqual(self.verify(), ("1.4.3", "1.4.3"))

    def test_homebrew_symlink_pair_is_supported(self):
        target_root = Path(self.candidates[0]).parent / "Cellar" / "clamav" / "bin"
        for name in ("clamscan", "freshclam"):
            target = self.make_executable(target_root / name)
            (Path(self.candidates[0]).parent / name).symlink_to(target)
        self.assertEqual(self.verify(), ("1.4.3", "1.4.3"))

    def test_uses_only_companion_updater_of_selected_scanner(self):
        self.make_pair(0, updater=False)
        self.make_pair(1, updater=True)
        with self.assertRaisesRegex(helper.DependencyVerificationError, "freshclam"):
            self.verify()

    def test_rejects_unsupported_malformed_and_prerelease_versions(self):
        self.make_pair()
        for value in ("ClamAV 1.6.0", "ClamAV 1.3.2", "ClamAV 1.4.0-rc1",
                      "ClamAV 1.4", "not clamav", "", "ClamAV 01.4.3"):
            with self.subTest(version=value):
                with self.assertRaises(helper.DependencyVerificationError):
                    self.verify(probe=lambda *_a, **_k: value)

    def test_updater_version_is_verified_and_must_match_release_branch(self):
        scanner = self.make_pair()
        def mismatched(command, **kwargs):
            return ("ClamAV 1.4.3" if command[0] == scanner
                    else "ClamAV 1.5.1")
        with self.assertRaisesRegex(helper.DependencyVerificationError, "incompatible"):
            self.verify(probe=mismatched)
        def unrecognized(command, **kwargs):
            return ("ClamAV 1.4.3" if command[0] == scanner else "not ClamAV")
        with self.assertRaisesRegex(helper.DependencyVerificationError, "updater version"):
            self.verify(probe=unrecognized)

    def test_probe_timeout_error_and_private_output_are_sanitized(self):
        self.make_pair()
        for error in (OSError("/Users/private/document.pdf"),
                      subprocess.TimeoutExpired("clamscan", 5),
                      subprocess.CalledProcessError(2, "clamscan")):
            with self.subTest(error=str(error)):
                with self.assertRaises(helper.DependencyVerificationError) as problem:
                    self.verify(probe=lambda *_a, **_k: (_ for _ in ()).throw(error))
                self.assertNotIn("/Users/", str(problem.exception))
        self.assertIsNone(helper.command_version(
            self.candidates[0], probe=lambda *_a, **_k: b"not-text"
        ))

    def test_runtime_scan_gate_and_supported_paths_remain_authoritative(self):
        scanner = (ROOT / "scan-and-open.py").read_text(encoding="utf-8")
        self.assertIn("require_supported_scanner_version(scanner)", scanner)
        self.assertIn("check_database()", scanner)
        self.assertIn("remove_quarantine", scanner)
        for candidate in helper.SCANNER_CANDIDATES:
            self.assertIn(repr(candidate), scanner)
        self.assertIn("1\\.(?:4|5)\\.[0-9]+", helper.VERSION.pattern)

    def test_installer_verifies_after_package_install_before_installed_file_changes(self):
        source = (ROOT / "install-allow-and-open.sh").read_text(encoding="utf-8")
        consent = 'python3 "$script_dir/scripts/confirm_clamav_install.py"'
        provisioning = 'HOMEBREW_NO_AUTO_UPDATE=1 "$brew_executable" install clamav'
        verify = 'python3 "$script_dir/scripts/verify_installed_clamav.py"'
        self.assertIn(consent, source)
        self.assertIn(provisioning, source)
        self.assertIn(verify, source)
        self.assertLess(source.index(consent), source.index(provisioning))
        self.assertLess(source.index(provisioning), source.index(verify))
        self.assertLess(source.index(verify), source.index('mkdir -p "$install_dir/signatures"'))
        self.assertLess(source.index(verify), source.index('bash "$install_dir/update-malware-signatures.sh"'))
        self.assertEqual(source.count(verify), 1)
        self.assertIn('scripts/report_install_prerequisites.py', source)
        ci = (ROOT / ".github/workflows/ci.yml").read_text(encoding="utf-8")
        self.assertIn("tests/clamav/post-install-verification.py -v", ci)

    def test_cli_fail_closed_no_stderr_leaks(self):
        with patch.object(helper, "verify_installed_dependencies",
                          side_effect=helper.DependencyVerificationError("ClamAV missing")):
            stderr = io.StringIO()
            with redirect_stderr(stderr):
                self.assertEqual(helper.main(), 1)
            self.assertIn("ClamAV dependency verification failed", stderr.getvalue())
        with patch.object(helper, "verify_installed_dependencies",
                          return_value=("1.4.3", "1.4.4")):
            stdout = io.StringIO()
            with redirect_stdout(stdout):
                self.assertEqual(helper.main(), 0)
            self.assertIn("Verified ClamAV scanner", stdout.getvalue())


if __name__ == "__main__":
    unittest.main()
