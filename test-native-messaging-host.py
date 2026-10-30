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
STATUS_SOURCE = ROOT / "native-messaging" / "HostStatus.swift"
STATUS_TEST = ROOT / "test-native-host-status.swift"


def frame(message):
  encoded = json.dumps(message, separators=(",", ":")).encode("utf-8")
  return struct.pack("<I", len(encoded)) + encoded


def ping(request_id="test_1"):
  return {"version": 1, "kind": "request", "topic": "host.ping",
          "requestId": request_id, "payload": None}


def handshake(request_id="hello_1", client_nonce="Client_Challenge_123456789"):
  return dict(ping(request_id), topic="host.handshake",
              payload={"clientNonce": client_nonce})


def handshake_response(request_id="hello_1", client_nonce="Client_Challenge_123456789"):
  return {"version": 1, "kind": "response", "topic": "host.handshake",
          "requestId": request_id, "payload": {
            "status": "transport-only", "protocolVersion": 1,
            "clientNonce": client_nonce, "scanAvailable": False}}


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
                    str(SOURCE), str(STATUS_SOURCE), "-o", str(cls.binary)],
                   capture_output=True, text=True, check=True, timeout=120)
    cls.status_binary = Path(cls.directory.name) / "native-host-status-tests"
    subprocess.run([compiler, "-parse-as-library", "-warnings-as-errors",
                    str(STATUS_SOURCE), str(STATUS_TEST), "-o", str(cls.status_binary)],
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

  def assert_handshake_response(self, reply, request_id="hello_1",
                                client_nonce="Client_Challenge_123456789"):
    self.assertEqual(reply["version"], 1)
    self.assertEqual(reply["kind"], "response")
    self.assertEqual(reply["topic"], "host.handshake")
    self.assertEqual(reply["requestId"], request_id)
    payload = reply["payload"]
    self.assertEqual(set(payload), {
      "status", "protocolVersion", "clientNonce", "scanAvailable",
      "applicationVersion", "activeProtectionProfile"
    })
    self.assertEqual(payload["status"], "transport-only")
    self.assertEqual(payload["protocolVersion"], 1)
    self.assertEqual(payload["clientNonce"], client_nonce)
    self.assertIs(payload["scanAvailable"], False)
    self.assertIn(payload["activeProtectionProfile"], ("built-in", None))
    if payload["applicationVersion"] is not None:
      self.assertRegex(payload["applicationVersion"], r"^[A-Za-z0-9.+-]{1,64}$")

  def test_read_only_status_snapshot_resolver(self):
    completed = subprocess.run([str(self.status_binary)], stdout=subprocess.PIPE,
                               stderr=subprocess.PIPE, timeout=10, check=False)
    self.assertEqual(completed.returncode, 0, completed.stderr.decode("utf-8"))
    self.assertEqual(completed.stdout, b"")
    self.assertEqual(completed.stderr, b"")

  def test_handshake_acknowledges_version_and_echoes_client_challenge(self):
    result = self.run_host(frame(handshake()))
    self.assertEqual(result.returncode, 0)
    self.assertEqual(result.stderr, b"")
    replies = responses(result.stdout)
    self.assertEqual(len(replies), 1)
    self.assert_handshake_response(replies[0])

  def test_handshake_is_one_time_and_connection_local(self):
    first = handshake()
    second = handshake("hello_2", "Another_Challenge_123456789")
    duplicate = self.run_host(frame(first) + frame(second))
    self.assertNotEqual(duplicate.returncode, 0)
    replies = responses(duplicate.stdout)
    self.assertEqual(len(replies), 1)
    self.assert_handshake_response(replies[0])
    self.assertEqual(duplicate.stderr, b"")

    # A fresh native host process has independent handshake state.
    for request in (first, second):
      with self.subTest(request=request["requestId"]):
        result = self.run_host(frame(request))
        self.assertEqual(result.returncode, 0)
        self.assertEqual(len(responses(result.stdout)), 1)

  def test_handshake_and_legacy_ping_can_share_one_connection(self):
    result = self.run_host(frame(ping("before")) + frame(handshake()) +
                           frame(ping("after")))
    self.assertEqual(result.returncode, 0)
    self.assertEqual(result.stderr, b"")
    replies = responses(result.stdout)
    self.assertEqual([r["topic"] for r in replies],
                     ["host.ping", "host.handshake", "host.ping"])
    self.assertEqual([r["requestId"] for r in replies],
                     ["before", "hello_1", "after"])
    self.assert_handshake_response(replies[1])
    self.assertEqual(replies[0]["payload"], replies[2]["payload"])

  def test_rejects_malformed_handshakes_without_reply(self):
    valid = handshake()
    invalid = [
      dict(valid, payload=None),
      dict(valid, payload={}),
      dict(valid, payload={"clientNonce": ""}),
      dict(valid, payload={"clientNonce": "too_short"}),
      dict(valid, payload={"clientNonce": "x" * 65}),
      dict(valid, payload={"clientNonce": "a" * 16 + "/"}),
      dict(valid, payload={"clientNonce": 1234567890123456}),
      dict(valid, payload={"clientNonce": True}),
      dict(valid, payload={"clientNonce": "a" * 16, "scanVerified": True}),
      dict(valid, version=2),
      dict(valid, kind="event"),
      dict(valid, topic="host.handshake", requestId="invalid/path"),
    ]
    for message in invalid:
      with self.subTest(message=message):
        result = self.run_host(frame(message))
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(result.stdout, b"")
        self.assertEqual(result.stderr, b"")

  def test_handshake_never_authorizes_native_pdf_actions(self):
    with tempfile.TemporaryDirectory(prefix="native-handshake-no-action-") as d:
      sentinel = Path(d) / "would-be-created"
      attack = dict(ping("open_1"), topic="pdf.open", payload={
        "path": str(sentinel), "command": "touch " + str(sentinel)})
      result = self.run_host(frame(handshake()) + frame(attack))
      self.assertNotEqual(result.returncode, 0)
      replies = responses(result.stdout)
      self.assertEqual(len(replies), 1)
      self.assert_handshake_response(replies[0])
      self.assertEqual(result.stderr, b"")
      self.assertFalse(sentinel.exists())

  def test_truncated_and_invalid_length_fail_closed(self):
    for data in (b"\x01", b"\x08\x00\x00\x00{}",
                 struct.pack("<I", 0), struct.pack("<I", 16385),
                 struct.pack("<I", 0xffffffff)):
      with self.subTest(data=data):
        result = self.run_host(data)
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(result.stdout, b"")
        self.assertEqual(result.stderr, b"")

  def test_rejects_non_json_and_invalid_encoding(self):
    for raw in (b"{", b"not json", b"\xff", b"[]", b"null"):
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

  def test_protocol_version_must_be_integer_one(self):
    for invalid in (0, -1, 2, 3, 1.0, True, False, "1", None):
      with self.subTest(version=invalid):
        result = self.run_host(frame(dict(ping(), version=invalid)))
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(result.stdout, b"")
        self.assertEqual(result.stderr, b"")

    # Preserve the exact JSON tokens: Python otherwise normalizes exponent forms.
    encoded = json.dumps(ping(), separators=(",", ":")).encode("utf-8")
    self.assertIn(b'"version":1', encoded)
    for literal in (b"1e0", b"1E+0", b"1.0000000000000001"):
      with self.subTest(literal=literal):
        body = encoded.replace(b'"version":1', b'"version":' + literal, 1)
        result = self.run_host(struct.pack("<I", len(body)) + body)
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(result.stdout, b"")
        self.assertEqual(result.stderr, b"")

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
