#!/usr/bin/env python3
"""Exercise the actual compiled, unregistered native messaging host process."""
import json
import os
from pathlib import Path
import shutil
import struct
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parent
SOURCE = ROOT / "native-messaging" / "Host.swift"


def frame(message):
  encoded = json.dumps(message, separators=(",", ":")).encode("utf-8")
  return struct.pack("<I", len(encoded)) + encoded


def ping(request_id="test_1"):
  return {"version": 1, "kind": "request", "topic": "host.ping",
          "requestId": request_id, "payload": None}


def responses(output):
  decoded = []
  while output:
    if len(output) < 4:
      raise AssertionError("Native host emitted unframed bytes")
    size = struct.unpack("<I", output[:4])[0]
    if not 0 < size <= 16384 or len(output) < 4 + size:
      raise AssertionError("Native host emitted an invalid frame")
    decoded.append(json.loads(output[4:4 + size]))
    output = output[4 + size:]
  return decoded


class NativeMessagingHostTests(unittest.TestCase):
  @classmethod
  def setUpClass(cls):
    cls.directory = tempfile.TemporaryDirectory(prefix="pdfmagic-native-host-")
    cls.binary = Path(cls.directory.name) / "pdf-magic-native-host"
    compiler = shutil.which("swiftc")
    if not compiler:
      cls.directory.cleanup()
      raise unittest.SkipTest("Swift compiler is required")
    subprocess.run([compiler, "-parse-as-library", "-warnings-as-errors",
                    str(SOURCE), "-o", str(cls.binary)],
                   capture_output=True, text=True, check=True, timeout=120)

  @classmethod
  def tearDownClass(cls):
    if hasattr(cls, "directory"):
      cls.directory.cleanup()

  def run_host(self, data, *args):
    return subprocess.run([str(self.binary), *args], input=data,
                          stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                          timeout=6, check=False)

  def test_compiled_host_is_executable(self):
    self.assertTrue(os.access(self.binary, os.X_OK))
    completed = self.run_host(b"")
    self.assertEqual(completed.returncode, 0)
    self.assertEqual(completed.stdout, b"")
    self.assertEqual(completed.stderr, b"")

  def test_liveness_is_explicitly_transport_only(self):
    result = self.run_host(frame(ping()))
    self.assertEqual(result.returncode, 0)
    self.assertEqual(result.stderr, b"")
    self.assertEqual(responses(result.stdout), [{
      "version": 1, "kind": "response", "topic": "host.ping",
      "requestId": "test_1", "payload": {
        "scanAvailable": False, "status": "transport-only"}
    }])

  def test_persistent_connection_handles_multiple_frames(self):
    result = self.run_host(frame(ping("first")) + frame(ping("second")))
    self.assertEqual(result.returncode, 0)
    self.assertEqual([message["requestId"] for message in responses(result.stdout)],
                     ["first", "second"])

  def test_truncated_and_invalid_length_fail_closed(self):
    for data in (b"\\x01", b"\\x08\\x00\\x00\\x00{}",
                 struct.pack("<I", 0), struct.pack("<I", 16385),
                 struct.pack("<I", 0xffffffff)):
      with self.subTest(data=data):
        result = self.run_host(data)
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(result.stdout, b"")
        self.assertEqual(result.stderr, b"")

  def test_rejects_non_json_and_invalid_encoding(self):
    for raw in (b"{", b"not json", b"\\xff", b"[]", b"null"):
      with self.subTest(raw=raw):
        result = self.run_host(struct.pack("<I", len(raw)) + raw)
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(result.stdout, b"")

  def test_rejects_non_liveness_topics_and_payloads(self):
    examples = [dict(ping(), topic="pdf.scan"),
                dict(ping(), topic="pdf.open"),
                dict(ping(), payload={"path": "/tmp/example.pdf"}),
                dict(ping(), payload={"verdict": "clean"})]
    for example in examples:
      with self.subTest(example=example):
        result = self.run_host(frame(example))
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(result.stdout, b"")

  def test_rejects_wrong_versions_kinds_and_extra_fields(self):
    for example in (dict(ping(), version=2), dict(ping(), version=True),
                    dict(ping(), kind="event"),
                    dict(ping(), origin="trusted"),
                    dict(ping(), requestId="bad id"),
                    dict(ping(), requestId="a" * 81)):
      with self.subTest(example=example):
        result = self.run_host(frame(example))
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(result.stdout, b"")

  def test_browser_supplied_origin_does_not_enable_a_scan(self):
    result = self.run_host(frame(ping()), "chrome-extension://exampleid/")
    self.assertEqual(result.returncode, 0)
    reply, = responses(result.stdout)
    self.assertFalse(reply["payload"]["scanAvailable"])

  def test_no_file_or_process_actions_from_untrusted_input(self):
    with tempfile.TemporaryDirectory(prefix="native-host-no-action-") as d:
      sentinel = Path(d) / "would-be-created"
      attack = dict(ping(), topic="pdf.open", payload={
        "path": str(sentinel), "command": "touch " + str(sentinel)})
      result = self.run_host(frame(attack))
      self.assertNotEqual(result.returncode, 0)
      self.assertFalse(sentinel.exists())
      self.assertEqual(result.stdout, b"")


if __name__ == "__main__":
  unittest.main()
