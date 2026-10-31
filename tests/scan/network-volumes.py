#!/usr/bin/env python3
"""opener-0843: mounted network volumes follow the ordinary fail-closed scan gate."""

from contextlib import ExitStack, contextmanager, nullcontext
import importlib.util
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location("mounted_volume_scan_gate", ROOT / "scan-and-open.py")
gate = importlib.util.module_from_spec(spec)
spec.loader.exec_module(gate)


class MountedVolumePolicyTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="mounted-volume-policy-")
        self.addCleanup(temporary.cleanup)
        # This stands in for a mounted SMB/NFS share: network behavior is
        # simulated at the filesystem metadata boundary without a live server.
        share = Path(temporary.name) / "mounted-share"
        share.mkdir()
        self.pdf = share / "document.pdf"
        self.original = b"%PDF-1.4\nnetwork volume content"
        self.pdf.write_bytes(self.original)
        self.bundle = share / "Example.app"
        self.bundle.mkdir()

    @contextmanager
    def isolated_scan(self, scanner_callback=None):
        with ExitStack() as stack:
            def mock(name, **kwargs):
                return stack.enter_context(patch.object(gate, name, **kwargs))

            mock("scan_slot", return_value=nullcontext())
            mock("active_scan_lock", return_value=nullcontext())
            mock("cached_clean", return_value=False)
            remembered = mock("remember_clean")
            mock("intended_destination", return_value="com.example.viewer")
            mock("pdf_fallback_application", return_value=None)
            mock("record_scan_destination")
            mock("record_opened_document_origin")
            mock("read_signature_database_version", return_value="known")
            mock("scan_engine_version", return_value="1.5.1")
            mock("verify_launch_target")
            mock("verify_local_file_available")
            mock("remove_quarantine")
            launched = mock("launch_clean_file")
            response = subprocess.CompletedProcess([], 0, "document: OK", "")
            if scanner_callback is None:
                scanned = mock("run_scan_command", return_value=response)
            else:
                scanned = mock("run_scan_command", side_effect=scanner_callback)
            yield scanned, launched, remembered

    def test_available_mounted_volume_uses_the_normal_scan_and_launch_gate(self):
        with patch.object(gate.os, "statvfs", return_value=object()) as probe, \
                self.isolated_scan() as (scanned, launched, remembered):
            self.assertEqual(gate.validate_scan_request(self.pdf), self.pdf)
            self.assertEqual(gate.supported_request_path(self.pdf), self.pdf)
            self.assertEqual(gate.validate_scan_request(self.bundle), self.bundle)
            result = gate.scan_and_open(self.pdf, "/scanner")

        self.assertEqual(result.status, "clean")
        self.assertIs(result.from_cache, False)
        scanned.assert_called_once()
        self.assertIn("--alert-encrypted=yes", scanned.call_args.args[0])
        self.assertIn("--alert-exceeds-max=yes", scanned.call_args.args[0])
        launched.assert_called_once_with(self.pdf, target_app="com.example.viewer")
        remembered.assert_called_once()
        self.assertGreaterEqual(probe.call_count, 4)
        self.assertEqual(self.pdf.read_bytes(), self.original)

    def test_offline_or_unreachable_mount_blocks_all_admission_paths(self):
        # Errors from a network filesystem must not expose mount/server names.
        with patch.object(gate.os, "statvfs",
                          side_effect=OSError("private-smb-server.example/share")), \
                patch.object(gate, "scan_slot") as queue, \
                patch.object(gate, "cached_clean") as cache, \
                patch.object(gate, "run_scan_command") as scanner, \
                patch.object(gate, "launch_clean_file") as launch:
            for validate in (gate.validate_scan_request, gate.supported_request_path):
                with self.subTest(validate=validate.__name__):
                    with self.assertRaises(RuntimeError) as caught:
                        validate(self.pdf)
                    self.assertEqual(str(caught.exception),
                                     gate.MOUNTED_VOLUME_UNAVAILABLE_MESSAGE)
                    self.assertEqual(gate.safe_scan_failure(caught.exception),
                                     gate.MOUNTED_VOLUME_UNAVAILABLE_MESSAGE)
            with self.assertRaises(RuntimeError):
                gate.scan_and_open(self.pdf, "/scanner")

        queue.assert_not_called()
        cache.assert_not_called()
        scanner.assert_not_called()
        launch.assert_not_called()
        self.assertEqual(self.pdf.read_bytes(), self.original)

    def test_mount_becoming_unavailable_during_scan_blocks_clean_handoff(self):
        state = {"offline": False}

        def check_mount(_):
            if state["offline"]:
                raise PermissionError("smb://private-share/unavailable")
            return object()

        def scan_then_disconnect(*_args, **_kwargs):
            state["offline"] = True
            return subprocess.CompletedProcess([], 0, "document: OK", "")

        with patch.object(gate.os, "statvfs", side_effect=check_mount), \
                self.isolated_scan(scan_then_disconnect) as (scanned, launched, remembered):
            with self.assertRaises(RuntimeError) as caught:
                gate.scan_and_open(self.pdf, "/scanner")
            self.assertEqual(str(caught.exception),
                             gate.MOUNTED_VOLUME_UNAVAILABLE_MESSAGE)
            self.assertEqual(gate.safe_scan_failure(caught.exception),
                             gate.MOUNTED_VOLUME_UNAVAILABLE_MESSAGE)

        scanned.assert_called_once()
        remembered.assert_not_called()
        launched.assert_not_called()
        self.assertEqual(self.pdf.read_bytes(), self.original)

    def test_remote_urls_remain_unsupported_not_auto_mounted(self):
        with patch.object(gate.os, "statvfs") as probe:
            for value in ("smb://private-server/share/document.pdf",
                          "nfs://private-server/document.pdf",
                          "https://private-server/document.pdf"):
                with self.subTest(scheme=value.split(":")[0]):
                    with self.assertRaisesRegex(RuntimeError,
                                                "Unsupported scan request type"):
                        gate.supported_request_path(value)
        probe.assert_not_called()


if __name__ == "__main__":
    unittest.main()
