#!/usr/bin/env python3
"""Real Safari PDF viewer smoke test. Only disposable Safari WebDriver + loopback.

--self-test runs without Safari and checks fixture/image contracts on Linux.
--live REQUIRES macOS SafariDriver, a working automation session, and actual
PDF color rendering. Missing automation, downloads, blank images or errors
FAIL; they must not be mistaken for a successful browser viewer test.
"""
import argparse
import base64
from contextlib import contextmanager
import json
import os
import socket
import struct
import subprocess
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen
import zlib

ROUTES = {
    "/safari-viewer.pdf": ("red", (0.88, 0.12, 0.12)),
    "/pdf-by-mime": ("blue", (0.10, 0.22, 0.86)),
}
PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"


def make_pdf(rgb):
    # A visible block of distinct color makes actual PDF *rendering*
    # observable, not just HTTP receipt, browser URL, or PDF metadata.
    red, green, blue = rgb
    stream = (
        f"{red:.2f} {green:.2f} {blue:.2f} rg 90 90 432 620 re f\n"
        "0 0 0 rg BT /F1 18 Tf 64 748 Td "
        "(PDF Magic Safari Viewer Test) Tj ET\n"
    ).encode("ascii")
    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        (b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] "
         b"/Resources << /Font << /F1 5 0 R >> >> /Contents 4 0 R >>"),
        b"<< /Length " + str(len(stream)).encode("ascii") +
        b" >>\nstream\n" + stream + b"endstream",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
    ]
    pdf = bytearray(b"%PDF-1.4\n")
    offsets = [0]
    for i, obj in enumerate(objects, start=1):
        offsets.append(len(pdf))
        pdf.extend(f"{i} 0 obj\n".encode("ascii") + obj + b"\nendobj\n")
    start_xref = len(pdf)
    pdf.extend(f"xref\n0 {len(offsets)}\n0000000000 65535 f \n".encode("ascii"))
    for offset in offsets[1:]:
        pdf.extend(f"{offset:010d} 00000 n \n".encode("ascii"))
    pdf.extend(
        (f"trailer\n<< /Size {len(offsets)} /Root 1 0 R >>\n"
         f"startxref\n{start_xref}\n%%EOF\n").encode("ascii")
    )
    return bytes(pdf)


def make_handler(counts):
    class PDFHandler(BaseHTTPRequestHandler):
        def do_GET(self):
            if self.path not in ROUTES:
                self.send_error(404)
                return
            pdf = make_pdf(ROUTES[self.path][1])
            counts[self.path] = counts.get(self.path, 0) + 1
            self.send_response(200)
            self.send_header("Content-Type", "application/pdf")
            self.send_header("Content-Disposition", "inline")
            self.send_header("Content-Length", str(len(pdf)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.end_headers()
            self.wfile.write(pdf)

        def log_message(self, format, *args):
            # No browsing history, user PDFs or request metadata in logs.
            return
    return PDFHandler


def sample_png_color(png, color):
    """Return fraction of screenshot pixels matching fixture's strong red/blue.

    Decode 8-bit RGB/RGBA noninterlaced PNG with standard row filters using
    only the Python stdlib. Unsupported/invalid screenshots fail explicitly.
    """
    if not png.startswith(PNG_SIGNATURE) or len(png) > 16_000_000:
        raise AssertionError("Missing or oversized WebDriver PNG screenshot")
    position, compressed, width, height, depth, kind, interlace = 8, bytearray(), 0, 0, 0, 0, 0
    while position < len(png):
        if position + 12 > len(png):
            raise AssertionError("Invalid PNG chunk")
        size = int.from_bytes(png[position:position + 4], "big")
        tag = png[position + 4:position + 8]
        start = position + 8
        if size > 16_000_000 or start + size + 4 > len(png):
            raise AssertionError("Malformed PNG length")
        payload = png[start:start + size]
        if tag == b"IHDR":
            width, height, depth, kind, _, _, interlace = struct.unpack(">IIBBBBB", payload)
        if tag == b"IDAT":
            compressed.extend(payload)
        position = start + size + 4
        if tag == b"IEND":
            break
    if not (64 <= width <= 10000 and 64 <= height <= 10000 and depth == 8 and
            kind in (2, 6) and interlace == 0):
        raise AssertionError("Safari screenshot has an unsupported PNG format")
    channels = 3 if kind == 2 else 4
    stride = width * channels
    data = zlib.decompress(bytes(compressed))
    if len(data) != (stride + 1) * height:
        raise AssertionError("Truncated or malformed screenshot raster")
    prev = bytearray(stride)
    count = total = index = 0
    for y in range(height):
        filter_type = data[index]
        index += 1
        row = bytearray(data[index:index + stride])
        index += stride
        if filter_type not in range(5):
            raise AssertionError("Unsupported PNG filter")
        for x in range(stride):
            a = row[x - channels] if x >= channels else 0
            b = prev[x]
            c = prev[x - channels] if x >= channels else 0
            if filter_type == 1:
                predict = a
            elif filter_type == 2:
                predict = b
            elif filter_type == 3:
                predict = (a + b) // 2
            elif filter_type == 4:
                p = a + b - c
                da, db, dc = abs(p - a), abs(p - b), abs(p - c)
                predict = a if da <= db and da <= dc else b if db <= dc else c
            else:
                predict = 0
            row[x] = (row[x] + predict) & 0xff
        if y % 4 == 0:
            for x in range(0, width, 4):
                p = x * channels
                r, g, b = row[p:p + 3]
                if color == "red":
                    match = r > 130 and r > g * 1.75 and r > b * 1.75
                else:
                    match = b > 135 and b > r * 1.75 and b > g * 1.35
                count += int(match)
                total += 1
        prev = row
    return count / total


def webdriver(method, port, path, body=None, timeout=30):
    data = None if body is None else json.dumps(body).encode("utf-8")
    req = Request(f"http://127.0.0.1:{port}{path}", data=data, method=method)
    if data is not None:
        req.add_header("Content-Type", "application/json; charset=utf-8")
    with urlopen(req, timeout=timeout) as response:
        result = json.load(response)
    value = result.get("value")
    if isinstance(value, dict) and "error" in value:
        raise RuntimeError("Safari WebDriver: " + str(value["error"]))
    return value


def get_free_port():
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


@contextmanager
def safari_driver():
    if sys.platform != "darwin" or not os.path.isfile("/usr/bin/safaridriver"):
        raise RuntimeError("Real Safari and its macOS WebDriver are required")
    port = get_free_port()
    proc = subprocess.Popen(
        ["/usr/bin/safaridriver", "-p", str(port)],
        stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    try:
        end = time.monotonic() + 30
        while time.monotonic() < end:
            if proc.poll() is not None:
                raise RuntimeError("SafariDriver exited without starting")
            try:
                webdriver("GET", port, "/status", timeout=2)
                break
            except (OSError, ValueError, RuntimeError):
                time.sleep(0.25)
        else:
            raise RuntimeError("SafariDriver did not become available")
        yield port
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait(timeout=5)


def verify_real_safari():
    counts = {}
    server = ThreadingHTTPServer(("127.0.0.1", 0), make_handler(counts))
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    session_id = None
    try:
        with safari_driver() as driver_port:
            result = webdriver("POST", driver_port, "/session", {
                "capabilities": {"alwaysMatch": {"browserName": "safari"}}
            }, timeout=45)
            session_id = result["sessionId"]
            caps = result["capabilities"]
            if caps.get("browserName", "").lower() != "safari":
                raise AssertionError("SafariDriver started the wrong browser")
            session = f"/session/{session_id}"
            webdriver("POST", driver_port, session + "/url", {"url": "about:blank"})
            blank = base64.b64decode(webdriver("GET", driver_port, session + "/screenshot"),
                                     validate=True)
            for route, (color, _) in ROUTES.items():
                url = f"http://127.0.0.1:{server.server_port}{route}"
                webdriver("POST", driver_port, session + "/url",
                          {"url": url}, timeout=45)
                end = time.monotonic() + 30
                observed_fraction = 0.0
                while time.monotonic() < end:
                    current = webdriver("GET", driver_port, session + "/url")
                    shot = base64.b64decode(
                        webdriver("GET", driver_port, session + "/screenshot"),
                        validate=True
                    )
                    observed_fraction = sample_png_color(shot, color)
                    # The browser must request the real PDF, retain its URL,
                    # and visibly render its colored content in its own viewport.
                    if (counts.get(route, 0) >= 1 and current == url and
                            shot != blank and observed_fraction >= 0.035):
                        break
                    time.sleep(0.5)
                else:
                    raise AssertionError(
                        f"Safari did not visibly render {route} as inline PDF "
                        f"(requested={counts.get(route, 0)}, color={observed_fraction:.4f})"
                    )
                print(f"PASS Safari PDF viewer: {route}, visible {color} page")
            print("PASS real Safari " + str(caps.get("browserVersion", "unknown")) +
                  " PDF viewer; no extension installed or scanner invoked")
    finally:
        if session_id is not None:
            try:
                webdriver("DELETE", driver_port, f"/session/{session_id}", timeout=10)
            except Exception:
                pass
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def png_test_image(color):
    # Construct synthetic RGB PNG and prove the pixel evidence decoder cannot
    # pass on metadata alone, white canvas, or a different color.
    width, height = 80, 80
    rgb = (224, 28, 28) if color == "red" else (20, 38, 221)
    raw = b"".join(b"\x00" + bytes(rgb) * width for _ in range(height))
    def chunk(tag, data):
        return (struct.pack(">I", len(data)) + tag + data +
                struct.pack(">I", zlib.crc32(tag + data) & 0xffffffff))
    return (PNG_SIGNATURE + chunk(b"IHDR",
        struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)) +
        chunk(b"IDAT", zlib.compress(raw)) + chunk(b"IEND", b""))


def self_test():
    for route, (color, rgb) in ROUTES.items():
        pdf = make_pdf(rgb)
        assert pdf.startswith(b"%PDF-1.4\n")
        assert pdf.rstrip().endswith(b"%%EOF")
        assert b"/Type /Page " in pdf
        assert b"/MediaBox [0 0 612 792]" in pdf
        assert b" re f\n" in pdf
        assert color in ("red", "blue")
        assert route.startswith("/")
    counts = {}
    server = ThreadingHTTPServer(("127.0.0.1", 0), make_handler(counts))
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        base = f"http://127.0.0.1:{server.server_port}"
        for route in ROUTES:
            with urlopen(base + route, timeout=3) as response:
                assert response.status == 200
                assert response.headers["Content-Type"] == "application/pdf"
                assert response.headers["Content-Disposition"] == "inline"
                assert response.headers["X-Content-Type-Options"] == "nosniff"
                assert response.headers["Cache-Control"] == "no-store"
                assert response.read().startswith(b"%PDF-1.4")
            assert counts[route] == 1
        try:
            urlopen(base + "/unlisted.pdf", timeout=3)
            raise AssertionError("Unknown path unexpectedly served")
        except HTTPError as error:
            assert error.code == 404
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)
    red = png_test_image("red")
    blue = png_test_image("blue")
    assert sample_png_color(red, "red") > .99
    assert sample_png_color(red, "blue") == 0
    assert sample_png_color(blue, "blue") > .99
    assert sample_png_color(blue, "red") == 0
    for bad in (b"", b"fakepng", PNG_SIGNATURE):
        try:
            sample_png_color(bad, "red")
            raise AssertionError("Malformed screenshot was accepted")
        except (AssertionError, ValueError, struct.error, zlib.error) as error:
            if str(error) == "Malformed screenshot was accepted":
                raise
    print("PASS Safari PDF fixture, local-only server, pixel evidence and fail-closed self-test")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    commands = parser.add_mutually_exclusive_group(required=True)
    commands.add_argument("--self-test", action="store_true")
    commands.add_argument("--live", action="store_true")
    args = parser.parse_args()
    if args.self_test:
        self_test()
    else:
        verify_real_safari()
