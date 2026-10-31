#!/usr/bin/env python3
"""opener-0821: Safari-downloaded PDF -> the existing managed scan/open gate.

--live drives actual Safari with SafariDriver on a disposable GitHub macOS
runner. It never launches a document: the final native-launch boundary is
recorded in a test double. --self-test exercises the same gate and fixtures
without claiming to have tested Safari on non-macOS machines.
"""
import argparse
from contextlib import ExitStack
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import importlib.util
import os
import re
import runpy
import sqlite3
import subprocess
import sys
import tempfile
import threading
import time
from unittest.mock import patch
from urllib.error import HTTPError
from urllib.request import urlopen
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[2]
PDF_BYTES = runpy.run_path(str(ROOT / "tests/browser/safari-pdf-viewer.py"))["make_pdf"](
    (0.2, 0.4, 0.7))
QUARANTINE_KEY = "com.apple.quarantine"
TEST_TAG = b"0081;00000000;Safari;00000000-0000-0000-0000-000000000000"
DOWNLOAD_ENDPOINT = "/download"
SAFARI_ELEMENT_KEY = "element-6066-11e4-a52e-4f735466cecf"


def make_handler(name, requests):
    assert re.fullmatch(r"pdfmagic-safari-[0-9a-f]{32}\.pdf", name)

    class DownloadHandler(BaseHTTPRequestHandler):
        def do_GET(self):
            if self.path == "/":
                body = (f'<!doctype html><title>Safari PDF download test</title>'
                        f'<a id="pdf-download" href="{DOWNLOAD_ENDPOINT}">'
                        "Download generated PDF</a>").encode("ascii")
                mimetype, disposition = "text/html; charset=utf-8", None
            elif self.path == DOWNLOAD_ENDPOINT:
                body = PDF_BYTES
                mimetype, disposition = "application/pdf", f'attachment; filename="{name}"'
                requests.append({"path": self.path, "agent": self.headers.get("User-Agent", "")})
            else:
                self.send_error(404)
                return
            self.send_response(200)
            self.send_header("Content-Type", mimetype)
            if disposition:
                self.send_header("Content-Disposition", disposition)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, format, *args):
            # No private paths or user browsing history in diagnostics.
            return
    return DownloadHandler


def ensure_safari_download(path, requests, timeout=35):
    """Never synthesize a downloaded file; require Safari's exact disk bytes."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if requests and path.is_file() and not path.is_symlink():
            contents = path.read_bytes()
            if contents == PDF_BYTES and path.stat().st_size == len(PDF_BYTES):
                if "Safari" not in requests[0]["agent"]:
                    raise AssertionError("Expected a real Safari browser request")
                return
        time.sleep(.25)
    raise AssertionError("Safari did not save the actual completed PDF download")


def load_opener():
    spec = importlib.util.spec_from_file_location("safari_scan_gate_under_test",
                                                   ROOT / "scan-and-open.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_managed_handoff(pdf, root, *, outcome):
    """Use the real scan_and_open decision flow with only external I/O mocked.

    The PDF is never replaced, copied from a local HTTP client, or passed to
    an actual application. Test the clean/cache and malware paths independently
    to prevent cached clean evidence from masking a rejected second verdict.
    """
    opener = load_opener()
    events = []
    assert pdf.read_bytes() == PDF_BYTES
    assert outcome in ("clean", "malware", "scanner-error")

    def scanned(command, timeout):
        assert command[0] == "/fixture-clamscan"
        assert "--alert-encrypted=yes" in command
        assert "--alert-exceeds-max=yes" in command
        assert "--max-scantime=0" in command
        assert command[-1] == str(pdf.resolve())
        events.append("scan")
        if outcome == "malware":
            # Benign fake ClamAV output, not actual malware or the EICAR pattern.
            return subprocess.CompletedProcess(command, 1, "fixture: Synthetic.Test FOUND\n", "")
        if outcome == "scanner-error":
            return subprocess.CompletedProcess(command, 2, "", "Scanner unavailable")
        return subprocess.CompletedProcess(command, 0, "fixture: OK\n", "")

    def verify(path, *, target_app=None):
        assert path == pdf.resolve()
        assert target_app == "com.apple.Safari"
        events.append("verify")

    def launch(path, *, target_app=None):
        assert path == pdf.resolve()
        assert target_app == "com.apple.Safari"
        assert pdf.read_bytes() == PDF_BYTES
        events.append("managed-launch")

    with ExitStack() as stack:
        for name, value in (
            ("CACHE_DB", root / (outcome + "-clean-cache.sqlite")),
            ("SCAN_REQUEST_DB", root / (outcome + "-requests.sqlite")),
            ("intended_destination", lambda path: "com.apple.Safari"),
            ("pdf_fallback_application", lambda **kwargs: None),
            ("verify_launch_target", verify),
            ("launch_clean_file", launch),
            ("run_scan_command", scanned),
            ("read_signature_database_version", lambda: None),
            ("scan_engine_version", lambda scanner: "1.4.0"),
        ):
            stack.enter_context(patch.object(opener, name, value))
        # Native --check-local is tested elsewhere, and the native binary is
        # absent from the standalone Safari CI job. Reject missing bytes here.
        stack.enter_context(patch.object(
            opener, "verify_local_file_available",
            side_effect=lambda path: (
                None if Path(path).is_file() and Path(path).read_bytes() == PDF_BYTES
                else (_ for _ in ()).throw(AssertionError("PDF unavailable"))
            )))
        if outcome == "clean":
            fresh = opener.scan_and_open(str(pdf), "/fixture-clamscan")
            cached = opener.scan_and_open(str(pdf), "/fixture-clamscan")
            assert fresh.status == cached.status == "clean"
            assert (fresh.from_cache, cached.from_cache) == (False, True)
            assert events == ["scan", "verify", "managed-launch",
                              "verify", "managed-launch"], events
            with sqlite3.connect(opener.SCAN_REQUEST_DB) as connection:
                targets = connection.execute(
                    "SELECT intended_destination_application FROM scan_requests "
                    "ORDER BY id").fetchall()
                origins = connection.execute(
                    "SELECT document_origin FROM opened_document_origins ORDER BY id"
                ).fetchall()
            assert targets == [("com.apple.Safari",)] * 2, targets
            assert origins == [("original",)] * 2, origins
        else:
            try:
                opener.scan_and_open(str(pdf), "/fixture-clamscan")
                raise AssertionError("Non-clean file was permitted to open")
            except RuntimeError as error:
                assert str(error) in (
                    "Malware was detected; opening was stopped.",
                    "The malware scan could not finish; opening was stopped.",
                ), str(error)
            assert events == ["scan"], events
    return events


def read_macos_quarantine(pdf):
    """Read the raw attribute bytes with macOS xattr; Python lacks os.getxattr."""
    result = subprocess.run(
        ["/usr/bin/xattr", "-px", QUARANTINE_KEY, str(pdf)],
        capture_output=True, check=False,
    )
    if result.returncode == 0:
        return bytes.fromhex(result.stdout.decode("ascii"))
    if b"No such xattr" in result.stderr:
        return None
    raise AssertionError("Could not inspect Safari download quarantine")


def test_pdf_handoff(pdf, root):
    # An existing Safari quarantine attribute must not be removed. On
    # loopback, Safari may omit it; attach a test-only marker in that case.
    original = None
    if sys.platform == "darwin":
        original = read_macos_quarantine(pdf)
        if original is None:
            subprocess.run(
                ["/usr/bin/xattr", "-wx", QUARANTINE_KEY, TEST_TAG.hex(), str(pdf)],
                capture_output=True, check=True,
            )
            original = read_macos_quarantine(pdf)
        assert original
    for result in ("clean", "malware", "scanner-error"):
        assert pdf.read_bytes() == PDF_BYTES
        test_managed_handoff(pdf, root, outcome=result)
        if original is not None:
            assert read_macos_quarantine(pdf) == original
    assert pdf.read_bytes() == PDF_BYTES
    print("PASS managed open after Safari PDF: clean/cache launch, malicious/error "
          "blocked, quarantine retained; launch only mocked")


def self_test():
    assert PDF_BYTES.startswith(b"%PDF-")
    assert PDF_BYTES.rstrip().endswith(b"%%EOF")
    requests = []
    name = "pdfmagic-safari-" + uuid4().hex + ".pdf"
    server = ThreadingHTTPServer(("127.0.0.1", 0), make_handler(name, requests))
    worker = threading.Thread(target=server.serve_forever, daemon=True)
    worker.start()
    try:
        base = f"http://127.0.0.1:{server.server_port}"
        with urlopen(base + "/", timeout=3) as response:
            assert response.headers["Content-Type"].startswith("text/html")
            assert b'id="pdf-download"' in response.read()
        with urlopen(base + DOWNLOAD_ENDPOINT, timeout=3) as response:
            assert response.headers["Content-Type"] == "application/pdf"
            assert response.headers["Content-Disposition"] == (
                f'attachment; filename="{name}"')
            assert response.headers["Cache-Control"] == "no-store"
            assert response.headers["X-Content-Type-Options"] == "nosniff"
            assert response.read() == PDF_BYTES
        try:
            urlopen(base + "/missing", timeout=3)
            raise AssertionError("Unknown HTTP endpoint was accepted")
        except HTTPError as error:
            assert error.code == 404
        assert len(requests) == 1
        with tempfile.TemporaryDirectory(prefix="pdfmagic-safari-gate-") as tmp:
            # This is a *synthetic* download fixture; only --live may claim
            # a PDF obtained from the actual Safari download manager.
            pdf = Path(tmp) / name
            pdf.write_bytes(PDF_BYTES)
            test_pdf_handoff(pdf, Path(tmp))
    finally:
        server.shutdown()
        server.server_close()
        worker.join(timeout=5)
    print("PASS portable Safari-download fixture/managed-opening regressions "
          "(no browser exercised)")


def live_test():
    if sys.platform != "darwin" or os.environ.get("GITHUB_ACTIONS") != "true" \
            or not os.environ.get("RUNNER_TEMP"):
        raise RuntimeError("Live Safari download test requires disposable macOS GitHub CI")
    from pathlib import Path
    driver = runpy.run_path(str(ROOT / "tests/browser/safari-pdf-viewer.py"))
    name = "pdfmagic-safari-" + uuid4().hex + ".pdf"
    downloads = Path.home() / "Downloads"
    downloads.mkdir(mode=0o700, exist_ok=True)
    pdf = downloads / name
    assert not pdf.exists(), "Unique Safari fixture destination must be unused"
    requests = []
    server = ThreadingHTTPServer(("127.0.0.1", 0), make_handler(name, requests))
    worker = threading.Thread(target=server.serve_forever, daemon=True)
    worker.start()
    session = None
    driver_port = None
    try:
        with driver["safari_driver"]() as driver_port:
            created = driver["webdriver"]("POST", driver_port, "/session", {
                "capabilities": {"alwaysMatch": {"browserName": "safari"}}
            }, timeout=45)
            session = created["sessionId"]
            assert created["capabilities"]["browserName"].lower() == "safari"
            url = f"http://127.0.0.1:{server.server_port}/"
            driver["webdriver"]("POST", driver_port, f"/session/{session}/url",
                                {"url": url}, timeout=45)
            element = driver["webdriver"](
                "POST", driver_port, f"/session/{session}/element",
                {"using": "css selector", "value": "#pdf-download"})
            assert SAFARI_ELEMENT_KEY in element
            driver["webdriver"]("POST", driver_port,
                                f"/session/{session}/element/"
                                f"{element[SAFARI_ELEMENT_KEY]}/click", {})
            ensure_safari_download(pdf, requests)
            with tempfile.TemporaryDirectory(
                    prefix="pdfmagic-safari-verdict-", dir=os.environ["RUNNER_TEMP"]) as tmp:
                test_pdf_handoff(pdf, Path(tmp))
            print("PASS actual Safari download and managed PDF open gate: Safari " +
                  str(created["capabilities"].get("browserVersion", "unknown")))
    finally:
        if session is not None:
            try:
                driver["webdriver"]("DELETE", driver_port,
                                    f"/session/{session}", timeout=10)
            except Exception:
                pass
        server.shutdown()
        server.server_close()
        worker.join(timeout=5)
        # Delete only the unique test artifact, never any existing user file.
        if pdf.is_file() and not pdf.is_symlink():
            pdf.unlink()


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    group = p.add_mutually_exclusive_group(required=True)
    group.add_argument("--self-test", action="store_true")
    group.add_argument("--live", action="store_true")
    args = p.parse_args()
    if args.self_test:
        self_test()
    else:
        live_test()
