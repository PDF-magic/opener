#!/usr/bin/env python3
"""opener-0489: enforce child-process restrictions in the isolated renderer."""

import errno
import os
from pathlib import Path
import subprocess
import sys
import unittest
from unittest.mock import patch

import maximum_isolated_renderer as renderer
import maximum_network_isolation as isolation


ROOT = Path(__file__).resolve().parent
ENV = {
    "PATH": "/usr/bin:/bin",
    "HOME": "/nonexistent",
    "LANG": "C",
    "PYTHONDONTWRITEBYTECODE": "1",
    "PYTHONNOUSERSITE": "1",
}

LINUX_PROBE = r'''
import errno, os, subprocess, sys, threading
sys.path.insert(0, sys.argv[1])
from maximum_network_isolation import apply_linux_child_process_denial
apply_linux_child_process_denial()

def denied(error):
    return error.errno in (errno.EPERM, errno.EACCES, errno.ENOSYS)

def check_fork():
    try:
        pid = os.fork()
    except OSError as error:
        return denied(error)
    if pid == 0:
        os._exit(0)
    os.waitpid(pid, 0)
    return False

def check_popen():
    try:
        child = subprocess.Popen(["/usr/bin/true"], close_fds=True)
    except OSError as error:
        return denied(error)
    child.wait(timeout=2)
    return False

def check_posix_spawn():
    try:
        pid = os.posix_spawn("/usr/bin/true", ["/usr/bin/true"], {})
    except OSError as error:
        return denied(error)
    os.waitpid(pid, 0)
    return False

def check_thread():
    finished = []
    worker = threading.Thread(target=lambda: finished.append(True))
    worker.start()
    worker.join(timeout=2)
    return finished == [True] and not worker.is_alive()

if all((check_fork(), check_popen(), check_posix_spawn(), check_thread())):
    raise SystemExit(0)
raise SystemExit(41)
'''

MACOS_PROBE = r'''
import errno, os, subprocess, sys, threading

def denied(error):
    return error.errno in (errno.EPERM, errno.EACCES, errno.ENOSYS)

def check_fork():
    try:
        pid = os.fork()
    except OSError as error:
        return denied(error)
    if pid == 0:
        os._exit(0)
    os.waitpid(pid, 0)
    return False

def check_popen():
    try:
        child = subprocess.Popen(["/usr/bin/true"], close_fds=True)
    except OSError as error:
        return denied(error)
    child.wait(timeout=2)
    return False

def check_posix_spawn():
    try:
        pid = os.posix_spawn("/usr/bin/true", ["/usr/bin/true"], {})
    except OSError as error:
        return denied(error)
    os.waitpid(pid, 0)
    return False

def check_thread():
    finished = []
    worker = threading.Thread(target=lambda: finished.append(True))
    worker.start()
    worker.join(timeout=2)
    return finished == [True] and not worker.is_alive()

if all((check_fork(), check_popen(), check_posix_spawn(), check_thread())):
    raise SystemExit(0)
raise SystemExit(41)
'''


class MaximumChildProcessRestrictionTests(unittest.TestCase):
    def test_renderer_profile_preserves_network_denial_and_denies_process_fork(self):
        profile = isolation.RENDERER_SANDBOX_PROFILE
        self.assertIn("(version 1)", profile)
        self.assertIn("(allow default)", profile)
        self.assertIn("(deny network*)", profile)
        self.assertIn("(deny process-fork)", profile)
        self.assertNotIn("allow process-fork", profile)

    def test_macos_renderer_command_uses_combined_restriction_profile(self):
        context = {
            "python": str(Path(sys.executable).resolve()),
            "worker": str((ROOT / "maximum_render_worker.py").resolve()),
            "worker_support": str((ROOT / "maximum_isolated_worker.py").resolve()),
            "network_support": str((ROOT / "maximum_network_isolation.py").resolve()),
            "renderer_support": str((ROOT / "maximum_isolated_renderer.py").resolve()),
            "python_prefix": str(Path(sys.prefix).resolve()),
            "python_base_prefix": str(Path(sys.base_prefix).resolve()),
        }
        with (
            patch.object(renderer.sys, "platform", "darwin"),
            patch.object(renderer, "_renderer_sandbox_context", return_value=context),
        ):
            command = renderer._renderer_command(
                ROOT / "maximum_render_worker.py", 0,
            )
        self.assertEqual(command[:3], (
            isolation.SANDBOX_EXEC, "-p", renderer.RENDERER_FILESYSTEM_PROFILE,
        ))
        self.assertIn("(deny default)", command[2])
        self.assertIn("(deny network*)", command[2])
        self.assertIn("(deny process-fork)", command[2])
        self.assertNotIn("(allow default)", command[2])
        self.assertNotIn("(allow file-write", command[2])

    @unittest.skipUnless(sys.platform == "linux", "Linux seccomp enforcement test")
    def test_linux_kernel_denies_fork_and_process_spawning_but_allows_threads(self):
        result = subprocess.run(
            [sys.executable, "-I", "-B", "-c", LINUX_PROBE, str(ROOT)],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=10,
            check=False,
            close_fds=True,
            start_new_session=True,
            cwd="/",
            env=ENV.copy(),
        )
        self.assertEqual(result.returncode, 0)

    @unittest.skipUnless(sys.platform == "darwin", "macOS Seatbelt enforcement test")
    def test_macos_kernel_denies_fork_and_process_spawning_but_allows_threads(self):
        if (not os.path.isfile(isolation.SANDBOX_EXEC)
                or not os.access(isolation.SANDBOX_EXEC, os.X_OK)):
            self.fail("The renderer process sandbox is unavailable")
        result = subprocess.run(
            [
                isolation.SANDBOX_EXEC, "-p", isolation.RENDERER_SANDBOX_PROFILE,
                sys.executable, "-I", "-B", "-c", MACOS_PROBE,
            ],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=10,
            check=False,
            close_fds=True,
            start_new_session=True,
            cwd="/",
            env=ENV.copy(),
        )
        self.assertEqual(result.returncode, 0)

    @unittest.skipUnless(sys.platform == "linux", "Linux seccomp enforcement test")
    def test_linux_restriction_fails_closed_when_filter_setup_is_unavailable(self):
        with patch.object(isolation.ctypes, "CDLL", side_effect=OSError("private runtime path")):
            with self.assertRaises(isolation.MaximumChildProcessRestrictionError) as error:
                isolation.apply_linux_child_process_denial()
        self.assertEqual(str(error.exception), isolation.CHILD_PROCESS_BLOCK_MESSAGE)

    def test_restriction_is_installed_before_pdf_read_and_renderer_import(self):
        source = (ROOT / "maximum_render_worker.py").read_text(encoding="utf-8")
        restriction = source.index("apply_linux_child_process_denial()")
        self.assertLess(restriction, source.index("document_bytes = sys.stdin.buffer.read"))
        self.assertLess(restriction, source.index("import pymupdf"))

    def test_installed_scanner_and_nonselectable_profile_are_unchanged(self):
        scanner = (ROOT / "scan-and-open.py").read_text(encoding="utf-8")
        self.assertNotIn("maximum_network_isolation", scanner)
        self.assertIn("if not cached_clean(cache_id):", scanner)
        from protection_profiles import ProtectionProfileID, PROTECTION_PROFILES
        self.assertFalse(PROTECTION_PROFILES[ProtectionProfileID.MAXIMUM].selectable)


if __name__ == "__main__":
    unittest.main()
