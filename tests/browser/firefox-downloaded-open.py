#!/usr/bin/env python3
"""Safely exercise the actual scan-and-open gate on Firefox-downloaded PDFs.

A real macOS Firefox WebDriver download supplies the path in CI. The native
scanner and actual application launcher are deliberately mocked: no unscanned
PDF may be opened and no user's PDF handler, profile or preferences are changed.
"""

from contextlib import ExitStack
import importlib.util
from pathlib import Path
import stat
import subprocess
import sys
import tempfile
from unittest.mock import patch

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
SPEC = importlib.util.spec_from_file_location(
    "firefox_download_scan_gate", ROOT / "scan-and-open.py"
)
opener = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(opener)

ATTRIBUTE = "com.apple.quarantine"
MARKER = b"0081;00000000;FirefoxPDFMagicTest;00000000-0000-0000-0000-000000000000"
NAMES = frozenset(("pdfmagic-attachment.pdf", "pdfmagic-octet.pdf"))
FIREFOX = "org.mozilla.firefox"


def checked_download(path):
    """Accept only regular files in a disposable Firefox fixture directory."""
    if path.name not in NAMES or path.parent.name != "downloads" or (
        not path.parent.parent.name.startswith("pdfmagic-firefox-native-download-")
    ):
        raise AssertionError("Expected an isolated Firefox fixture download")
    if path.is_symlink() or not stat.S_ISREG(path.lstat().st_mode):
        raise AssertionError("Only a regular downloaded PDF may enter the test")
    data = path.read_bytes()
    if not data.startswith(b"%PDF-1.") or b"%%EOF" not in data[-64:]:
        raise AssertionError("The saved file is not the expected PDF")
    return data


def read_quarantine(path):
    """Read exact xattr bytes with macOS's native tool, never deleting metadata."""
    if sys.platform != "darwin":
        return None
    result = subprocess.run(
        ["/usr/bin/xattr", "-px", ATTRIBUTE, str(path)],
        capture_output=True,
    )
    if result.returncode == 0:
        return bytes.fromhex(result.stdout.decode("ascii"))
    if b"No such xattr" in result.stderr:
        return None
    raise RuntimeError("The macOS quarantine attribute could not be read")


def quarantine_marker(path):
    """Preserve Firefox's native marker, or seed one if this CI profile lacks it."""
    if sys.platform != "darwin":
        return None, "not-applicable"
    existing = read_quarantine(path)
    if existing is not None:
        if not existing:
            raise AssertionError("Empty quarantine value is not a valid marker")
        return existing, "firefox-set"
    # Test-only creation, never removal: macOS Python lacks os.setxattr.
    subprocess.run(
        ["/usr/bin/xattr", "-w", ATTRIBUTE, MARKER.decode("ascii"), str(path)],
        capture_output=True, check=True,
    )
    return read_quarantine(path), "seeded-in-test"


def scenario(path, label, verdict, *, verified=True, timeout=False):
    """Use real production scan gating with fake external scanner and GUI open."""
    events = []

    def scan(command, **kwargs):
        if command[0] != "/scanner":
            raise AssertionError("Unexpected external command")
        if command[1:] == ["--version"]:
            return subprocess.CompletedProcess(command, 0, "ClamAV test/1", "")
        if Path(command[-1]).resolve() != path.resolve() or "--alert-encrypted=yes" not in command:
            raise AssertionError("The scanner must inspect the exact download")
        events.append(("scan", tuple(command)))
        if timeout:
            raise subprocess.TimeoutExpired(command, 1)
        return subprocess.CompletedProcess(
            command, verdict,
            "pdf: OK" if verdict == 0 else "pdf: Eicar-Test-Signature FOUND",
            ""
        )

    def verify(file_path, target_app=None):
        events.append(("verify", str(file_path), target_app))
        if Path(file_path).resolve() != path.resolve() or target_app != FIREFOX:
            raise AssertionError("The selected Firefox destination must be pinned")
        if not verified:
            raise RuntimeError("PDF target unavailable; opening was stopped.")

    def launch(file_path, target_app=None):
        if Path(file_path).resolve() != path.resolve() or target_app != FIREFOX:
            raise AssertionError("The selected Firefox destination changed")
        events.append(("launch", str(file_path), target_app))

    with tempfile.TemporaryDirectory(prefix="pdfmagic-firefox-scan-gate-") as tmp:
        with ExitStack() as stack:
            stack.enter_context(patch.object(opener, "CACHE_DB", Path(tmp) / "cache.sqlite"))
            stack.enter_context(patch.object(opener, "SCAN_REQUEST_DB", Path(tmp) / "requests.sqlite"))
            stack.enter_context(patch.object(opener, "intended_destination", return_value=FIREFOX))
            stack.enter_context(patch.object(opener, "pdf_fallback_application", return_value=None))
            stack.enter_context(patch.object(opener, "record_scan_destination"))
            stack.enter_context(patch.object(opener, "record_opened_document_origin"))
            stack.enter_context(patch.object(opener, "verify_local_file_available"))
            stack.enter_context(patch.object(opener, "verify_launch_target", side_effect=verify))
            stack.enter_context(patch.object(opener, "launch_clean_file", side_effect=launch))
            stack.enter_context(patch.object(opener, "scan_engine_version", return_value=None))
            stack.enter_context(patch.object(opener, "read_signature_database_version", return_value=None))
            stack.enter_context(patch.object(opener.subprocess, "run", side_effect=scan))

            if verdict == 0 and verified and not timeout:
                fresh = opener.scan_and_open(str(path), "/scanner")
                cached = opener.scan_and_open(str(path), "/scanner")
                if (fresh.status, cached.status) != ("clean", "clean") or (
                    fresh.from_cache, cached.from_cache
                ) != (False, True):
                    raise AssertionError("Fresh and cached scans must retain clean verdicts")
                if [event[0] for event in events] != [
                    "scan", "verify", "launch", "verify", "launch"
                ]:
                    raise AssertionError("Safe opening must follow scan and verification")
            else:
                try:
                    opener.scan_and_open(str(path), "/scanner")
                except RuntimeError as error:
                    if timeout and "timed out" not in str(error):
                        raise
                    if verdict != 0 and "Malware" not in str(error):
                        raise
                    if not verified and "opening was stopped" not in str(error):
                        raise
                else:
                    raise AssertionError("A blocked or unverified PDF was opened")
                expected = ["scan", "verify"] if not verified and not timeout and verdict == 0 else ["scan"]
                if [event[0] for event in events] != expected:
                    raise AssertionError("Unsafe PDF must never reach the launcher")
    return label


def verify_download(path):
    # macOS aliases /var to /private/var; compare the scanner\'s canonical path.
    path = path.resolve(strict=True)
    data = checked_download(path)
    original, origin = quarantine_marker(path)
    for name, verdict, verified, timeout in [
        ("clean-and-cached", 0, True, False),
        ("malware-blocked", 1, True, False),
        ("missing-target-blocked", 0, False, False),
        ("scan-timeout-blocked", 0, True, True)
    ]:
        scenario(path, name, verdict, verified=verified, timeout=timeout)
        if path.read_bytes() != data:
            raise AssertionError("The download bytes changed during a scan or handoff")
        if original is not None and read_quarantine(path) != original:
            raise AssertionError("The existing macOS quarantine marker was changed")
    print("PASS Firefox-downloaded PDF scan-and-open isolation (" + origin + ")")


def main(argv):
    if len(argv) == 1 and argv[0] == "--self-test":
        with tempfile.TemporaryDirectory(
            prefix="pdfmagic-firefox-native-download-"
        ) as temp:
            directory = Path(temp) / "downloads"
            directory.mkdir()
            for name in sorted(NAMES):
                pdf = directory / name
                pdf.write_bytes(
                    b"%PDF-1.4\n1 0 obj <</Type /Catalog>> endobj\n%%EOF\n"
                )
                verify_download(pdf)
        return
    if len(argv) != 1 or sys.platform != "darwin":
        raise SystemExit("Expected one macOS Firefox fixture PDF, or --self-test")
    verify_download(Path(argv[0]))


if __name__ == "__main__":
    main(sys.argv[1:])
