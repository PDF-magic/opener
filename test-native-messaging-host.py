#!/usr/bin/env python3
"""Exercise the actual compiled, unregistered native messaging host process."""
import json
import os
from pathlib import Path
import shutil
import struct
import subprocess
import tempfile
import time
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


def health(request_id="health_1"):
  return dict(ping(request_id), topic="host.health")


def health_reply(request_id="health_1"):
  return {"version": 1, "kind": "response", "topic": "host.health",
          "requestId": request_id, "payload": {
            "status": "transport-only", "transportResponsive": True,
            "scannerHealth": None, "scanAvailable": False,
            "authorizesOpen": False}}


def handshake(request_id="hello_1", client_nonce="Client_Challenge_123456789"):
  return dict(ping(request_id), topic="host.handshake",
              payload={"clientNonce": client_nonce})


def handshake_response(request_id="hello_1", client_nonce="Client_Challenge_123456789"):
  return {"version": 1, "kind": "response", "topic": "host.handshake",
          "requestId": request_id, "payload": {
            "status": "transport-only", "protocolVersion": 1,
            "clientNonce": client_nonce, "scanAvailable": False}}


def scan_request(request_id="scan_1"):
  return dict(ping(request_id), topic="scan.request",
              payload={"intent": "user-selected-pdf"})


def unavailable_scan_reply(request_id="scan_1"):
  return {"version": 1, "kind": "response", "topic": "scan.request",
          "requestId": request_id, "payload": {
            "status": "unavailable",
            "reason": "trusted-scan-coordinator-required",
            "scanAvailable": False, "scanStarted": False,
            "scanVerified": False, "authorizesOpen": False}}


def scan_status(request_id="status_1", scan_request_id="scan_1"):
  return dict(ping(request_id), topic="scan.status",
              payload={"scanRequestId": scan_request_id})


def unavailable_status_reply(request_id="status_1", scan_request_id="scan_1"):
  return {"version": 1, "kind": "response", "topic": "scan.status",
          "requestId": request_id, "payload": {
            "scanRequestId": scan_request_id,
            "status": "unavailable",
            "reason": "trusted-scan-coordinator-required",
            "scanAvailable": False, "scanStarted": False,
            "scanVerified": False, "authorizesOpen": False}}


def scan_result(request_id="result_1", scan_request_id="scan_1"):
  return dict(ping(request_id), topic="scan.result",
              payload={"scanRequestId": scan_request_id})


def unavailable_result_reply(request_id="result_1", scan_request_id="scan_1"):
  return {"version": 1, "kind": "response", "topic": "scan.result",
          "requestId": request_id, "payload": {
            "scanRequestId": scan_request_id,
            "status": "unavailable",
            "reason": "trusted-scan-coordinator-required",
            "result": None, "scanCompleted": False,
            "scanVerified": False, "authorizesOpen": False}}


def scan_cancel(request_id="cancel_1", scan_request_id="scan_1"):
  return dict(ping(request_id), topic="scan.cancel",
              payload={"scanRequestId": scan_request_id})


def unavailable_cancel_reply(request_id="cancel_1", scan_request_id="scan_1"):
  return {"version": 1, "kind": "response", "topic": "scan.cancel",
          "requestId": request_id, "payload": {
            "scanRequestId": scan_request_id,
            "status": "unavailable",
            "reason": "trusted-scan-coordinator-required",
            "cancellationAccepted": False, "cancelled": False,
            "scanStarted": False, "scanVerified": False,
            "authorizesOpen": False}}


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

  def assert_diagnostics(self, completed):
    # Success is silent. Rejected inputs only emit fixed, path-free codes on
    # stderr; stdout must always contain exclusively native protocol frames.
    if completed.returncode == 0:
      self.assertEqual(completed.stderr, b"")
    else:
      self.assertIn(completed.stderr, (
        b"pdf-magic-native-host: invalid-frame\n",
        b"pdf-magic-native-host: invalid-message\n"
      ))

  def test_compiled_host_is_executable(self):
    self.assertTrue(os.access(self.binary, os.X_OK))
    completed = self.run_host(b"")
    self.assertEqual(completed.returncode, 0)
    self.assertEqual(completed.stdout, b"")
    self.assert_diagnostics(completed)

  def test_liveness_is_explicitly_transport_only(self):
    result = self.run_host(frame(ping()))
    self.assertEqual(result.returncode, 0)
    self.assert_diagnostics(result)
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

  def test_health_check_requires_completed_handshake_not_just_ping(self):
    for prefix in (b"", frame(ping("probe_1"))):
      with self.subTest(has_ping=bool(prefix)):
        run = self.run_host(prefix + frame(health()))
        self.assertNotEqual(run.returncode, 0)
        self.assert_diagnostics(run)
        replies = responses(run.stdout)
        self.assertEqual(len(replies), int(bool(prefix)))
        if replies:
          self.assertEqual(replies[0]["topic"], "host.ping")

  def test_health_check_correlates_without_claiming_scanner_health(self):
    run = self.run_host(
      frame(handshake()) + frame(health()) +
      frame(scan_request("scan_1")) + frame(scan_cancel("cancel_1", "scan_1")) +
      frame(health("health_2")) + frame(ping("still_alive"))
    )
    self.assertEqual(run.returncode, 0)
    self.assert_diagnostics(run)
    replies = responses(run.stdout)
    self.assertEqual(len(replies), 6)
    self.assert_handshake_response(replies[0])
    self.assertEqual(replies[1], health_reply())
    self.assertEqual(replies[2], unavailable_scan_reply("scan_1"))
    self.assertEqual(replies[3], unavailable_cancel_reply("cancel_1", "scan_1"))
    self.assertEqual(replies[4], health_reply("health_2"))
    self.assertEqual(replies[5]["payload"],
                     {"status": "transport-only", "scanAvailable": False})
    for health_response in (replies[1], replies[4]):
      payload = health_response["payload"]
      self.assertIs(payload["transportResponsive"], True)
      self.assertIsNone(payload["scannerHealth"])
      self.assertIs(payload["scanAvailable"], False)
      self.assertIs(payload["authorizesOpen"], False)
      for forbidden in ("scanVerified", "scanResult", "filePath", "activeProtectionProfile"):
        self.assertNotIn(forbidden, payload)

  def test_health_check_rejects_untrusted_payloads_and_envelopes(self):
    valid = health()
    invalid = [
      dict(valid, payload={}),
      dict(valid, payload={"path": "/private/secret.pdf"}),
      dict(valid, payload={"scannerHealthy": True}),
      dict(valid, payload={"authorizesOpen": True}),
      dict(valid, payload={"scanAvailable": True}),
      dict(valid, payload=[]),
      dict(valid, payload=False),
      dict(valid, payload="ping"),
      dict(valid, kind="event"),
      dict(valid, kind="response"),
      dict(valid, version=2),
      dict(valid, requestId="../invalid"),
    ]
    for request in invalid:
      with self.subTest(request=request):
        run = self.run_host(frame(handshake()) + frame(request))
        self.assertNotEqual(run.returncode, 0)
        self.assert_diagnostics(run)
        replies = responses(run.stdout)
        self.assertEqual(len(replies), 1)
        self.assert_handshake_response(replies[0])

  def test_health_check_does_not_read_or_modify_pdf(self):
    with tempfile.TemporaryDirectory(prefix="native-health-read-only-") as directory:
      document = Path(directory) / "private.pdf"
      original = b"%PDF-1.4\nprivate fixture remains untouched"
      document.write_bytes(original)
      # Unknown caller fields cannot turn a health check into a file probe.
      attack = dict(health(), payload={"path": str(document)})
      rejected = self.run_host(frame(handshake()) + frame(attack))
      self.assertNotEqual(rejected.returncode, 0)
      self.assertEqual(len(responses(rejected.stdout)), 1)
      self.assert_diagnostics(rejected)
      self.assertNotIn(original, rejected.stdout)
      accepted = self.run_host(frame(handshake()) + frame(health()))
      self.assertEqual(accepted.returncode, 0)
      self.assertEqual(responses(accepted.stdout)[1], health_reply())
      self.assert_diagnostics(accepted)
      self.assertEqual(document.read_bytes(), original)

  def test_read_only_status_snapshot_resolver(self):
    completed = subprocess.run([str(self.status_binary)], stdout=subprocess.PIPE,
                               stderr=subprocess.PIPE, timeout=10, check=False)
    self.assertEqual(completed.returncode, 0, completed.stderr.decode("utf-8"))
    self.assertEqual(completed.stdout, b"")
    self.assert_diagnostics(completed)

  def test_handshake_acknowledges_version_and_echoes_client_challenge(self):
    result = self.run_host(frame(handshake()))
    self.assertEqual(result.returncode, 0)
    self.assert_diagnostics(result)
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
    self.assert_diagnostics(duplicate)

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
    self.assert_diagnostics(result)
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
        self.assert_diagnostics(result)

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
      self.assert_diagnostics(result)
      self.assertFalse(sentinel.exists())

  def test_scan_request_requires_completed_handshake(self):
    result = self.run_host(frame(scan_request()))
    self.assertNotEqual(result.returncode, 0)
    self.assertEqual(result.stdout, b"")
    self.assert_diagnostics(result)

    # A successful ping is not a handshake or an authorization.
    result = self.run_host(frame(ping("ping_1")) + frame(scan_request()))
    self.assertNotEqual(result.returncode, 0)
    self.assertEqual(responses(result.stdout)[0]["topic"], "host.ping")
    self.assertEqual(len(responses(result.stdout)), 1)
    self.assert_diagnostics(result)

  def test_scan_request_returns_correlated_explicit_unavailability(self):
    result = self.run_host(frame(handshake()) + frame(scan_request()))
    self.assertEqual(result.returncode, 0)
    self.assert_diagnostics(result)
    replies = responses(result.stdout)
    self.assertEqual(len(replies), 2)
    self.assert_handshake_response(replies[0])
    self.assertEqual(replies[1], unavailable_scan_reply())
    self.assertFalse(replies[1]["payload"]["scanStarted"])
    self.assertFalse(replies[1]["payload"]["authorizesOpen"])

  def test_scan_request_never_mutates_handshake_or_ping(self):
    result = self.run_host(
      frame(handshake()) +
      frame(scan_request("manual_1")) +
      frame(ping("check_1")) +
      frame(scan_request("manual_2"))
    )
    self.assertEqual(result.returncode, 0)
    self.assert_diagnostics(result)
    replies = responses(result.stdout)
    self.assertEqual(len(replies), 4)
    self.assert_handshake_response(replies[0])
    self.assertEqual(replies[1], unavailable_scan_reply("manual_1"))
    self.assertEqual(replies[2]["topic"], "host.ping")
    self.assertEqual(replies[2]["payload"],
                     {"status": "transport-only", "scanAvailable": False})
    self.assertEqual(replies[3], unavailable_scan_reply("manual_2"))

  def test_scan_request_rejects_paths_claimed_verdicts_and_malformed_intent(self):
    good = scan_request()
    invalid = [
      dict(good, payload=None),
      dict(good, payload={}),
      dict(good, payload={"intent": True}),
      dict(good, payload={"intent": 1}),
      dict(good, payload={"intent": "pdf.open"}),
      dict(good, payload={"intent": "browser-download"}),
      dict(good, payload={"intent": "user-selected-pdf", "path": "/tmp/file.pdf"}),
      dict(good, payload={"intent": "user-selected-pdf", "downloadId": 12}),
      dict(good, payload={"intent": "user-selected-pdf", "sourceUrl": "https://invalid.example/"}),
      dict(good, payload={"intent": "user-selected-pdf", "scanVerified": True}),
      dict(good, payload={"intent": "user-selected-pdf", "protectionLevel": "off"}),
      dict(good, payload=["user-selected-pdf"]),
      dict(good, kind="event"),
      dict(good, version=2),
      dict(good, requestId="../secret"),
      dict(good, topic="pdf.scan"),
    ]
    for request in invalid:
      with self.subTest(request=request):
        result = self.run_host(frame(handshake()) + frame(request))
        self.assertNotEqual(result.returncode, 0)
        self.assert_diagnostics(result)
        replies = responses(result.stdout)
        self.assertEqual(len(replies), 1)
        self.assert_handshake_response(replies[0])

  def test_scan_request_never_reads_or_opens_caller_paths(self):
    with tempfile.TemporaryDirectory(prefix="native-scan-request-inert-") as d:
      private_file = Path(d) / "private.pdf"
      private_file.write_bytes(b"private contents are not native messages")
      bad = dict(scan_request(), payload={
        "intent": "user-selected-pdf", "path": str(private_file)
      })
      result = self.run_host(frame(handshake()) + frame(bad))
      self.assertNotEqual(result.returncode, 0)
      self.assert_diagnostics(result)
      self.assertNotIn(str(private_file).encode(), result.stdout)
      self.assertNotIn(private_file.read_bytes(), result.stdout)
      self.assertEqual(private_file.read_bytes(),
                       b"private contents are not native messages")

      # Even a valid request does not scan, launch, or alter the file.
      result = self.run_host(frame(handshake()) + frame(scan_request()))
      self.assertEqual(result.returncode, 0)
      self.assertEqual(responses(result.stdout)[1], unavailable_scan_reply())
      self.assertEqual(private_file.read_bytes(),
                       b"private contents are not native messages")

  def test_scan_status_requires_handshake_not_just_ping(self):
    for prefix in (b"", frame(ping("live_1"))):
      with self.subTest(prefix=bool(prefix)):
        result = self.run_host(prefix + frame(scan_status()))
        self.assertNotEqual(result.returncode, 0)
        self.assert_diagnostics(result)
        expected = [] if not prefix else [{
          "version": 1, "kind": "response", "topic": "host.ping",
          "requestId": "live_1", "payload": {
            "status": "transport-only", "scanAvailable": False}
        }]
        self.assertEqual(responses(result.stdout), expected)

  def test_scan_status_correlates_without_fabricating_progress(self):
    result = self.run_host(frame(handshake()) +
                           frame(scan_request("scan_1")) +
                           frame(scan_status("check_1", "scan_1")))
    self.assertEqual(result.returncode, 0)
    self.assert_diagnostics(result)
    replies = responses(result.stdout)
    self.assertEqual(len(replies), 3)
    self.assert_handshake_response(replies[0])
    self.assertEqual(replies[1], unavailable_scan_reply("scan_1"))
    self.assertEqual(replies[2], unavailable_status_reply("check_1", "scan_1"))
    status = replies[2]["payload"]
    self.assertIs(status["scanStarted"], False)
    self.assertIs(status["scanVerified"], False)
    self.assertIs(status["authorizesOpen"], False)
    self.assertNotIn("percentComplete", status)
    self.assertNotIn("scanResult", status)
    self.assertNotIn("path", status)

  def test_scan_status_unknown_and_repeated_ids_remain_unavailable(self):
    # No trusted coordinator exists: neither a correlated ID nor a prior
    # scan.request acknowledgment establishes a real scanner job.
    messages = [handshake(), scan_status("first", "unknown"),
                scan_request("manual_1"), ping("still_alive"),
                scan_status("second", "manual_1"),
                scan_status("third", "unknown")]
    result = self.run_host(b"".join(frame(m) for m in messages))
    self.assertEqual(result.returncode, 0)
    self.assert_diagnostics(result)
    replies = responses(result.stdout)
    self.assertEqual(len(replies), len(messages))
    self.assert_handshake_response(replies[0])
    self.assertEqual(replies[1], unavailable_status_reply("first", "unknown"))
    self.assertEqual(replies[2], unavailable_scan_reply("manual_1"))
    self.assertEqual(replies[3]["payload"],
                     {"status": "transport-only", "scanAvailable": False})
    self.assertEqual(replies[4], unavailable_status_reply("second", "manual_1"))
    self.assertEqual(replies[5], unavailable_status_reply("third", "unknown"))

    # A fresh host process cannot claim jobs from a prior connection.
    fresh = self.run_host(frame(handshake()) +
                          frame(scan_status("fresh", "manual_1")))
    self.assertEqual(fresh.returncode, 0)
    self.assertEqual(responses(fresh.stdout)[1],
                     unavailable_status_reply("fresh", "manual_1"))

  def test_scan_status_rejects_malformed_queries_and_claims(self):
    valid = scan_status()
    malformed = [
      dict(valid, payload=None),
      dict(valid, payload={}),
      dict(valid, payload=[]),
      dict(valid, payload={"scanRequestId": ""}),
      dict(valid, payload={"scanRequestId": "x" * 81}),
      dict(valid, payload={"scanRequestId": "has space"}),
      dict(valid, payload={"scanRequestId": "../private.pdf"}),
      dict(valid, payload={"scanRequestId": 42}),
      dict(valid, payload={"scanRequestId": True}),
      dict(valid, payload={"scanRequestId": None}),
      dict(valid, payload={"scanRequestId": ["scan_1"]}),
      dict(valid, payload={"scanRequestId": "scan_1", "path": "/tmp/private.pdf"}),
      dict(valid, payload={"scanRequestId": "scan_1", "status": "clean"}),
      dict(valid, payload={"scanRequestId": "scan_1", "authorizesOpen": True}),
      dict(valid, payload={"scanRequestId": "scan_1", "scanVerified": True}),
      dict(valid, payload={"scanRequestId": "scan_1", "protectionLevel": "off"}),
      dict(valid, kind="event"),
      dict(valid, version=2),
      dict(valid, requestId="bad/id"),
      dict(valid, topic="pdf.status"),
    ]
    for request in malformed:
      with self.subTest(request=request):
        result = self.run_host(frame(handshake()) + frame(request))
        self.assertNotEqual(result.returncode, 0)
        self.assert_diagnostics(result)
        replies = responses(result.stdout)
        self.assertEqual(len(replies), 1)
        self.assert_handshake_response(replies[0])

  def test_scan_status_never_reads_file_paths_or_starts_a_scan(self):
    with tempfile.TemporaryDirectory(prefix="native-scan-status-inert-") as d:
      sentinel = Path(d) / "private.pdf"
      original = b"private file contents must remain untouched"
      sentinel.write_bytes(original)
      invalid = dict(scan_status(), payload={"scanRequestId": str(sentinel)})
      refused = self.run_host(frame(handshake()) + frame(invalid))
      self.assertNotEqual(refused.returncode, 0)
      self.assert_diagnostics(refused)
      self.assertNotIn(str(sentinel).encode(), refused.stdout)
      self.assertNotIn(original, refused.stdout)
      self.assertEqual(sentinel.read_bytes(), original)

      accepted = self.run_host(frame(handshake()) + frame(scan_status()))
      self.assertEqual(accepted.returncode, 0)
      self.assert_diagnostics(accepted)
      self.assertEqual(responses(accepted.stdout)[1], unavailable_status_reply())
      self.assertEqual(sentinel.read_bytes(), original)

  def test_scan_result_requires_completed_handshake(self):
    for prefix in (b"", frame(ping("probe"))):
      with self.subTest(ping=bool(prefix)):
        run = self.run_host(prefix + frame(scan_result()))
        self.assertNotEqual(run.returncode, 0)
        self.assert_diagnostics(run)
        replies = responses(run.stdout)
        self.assertEqual(len(replies), 1 if prefix else 0)
        if replies:
          self.assertEqual(replies[0]["topic"], "host.ping")
          self.assertFalse(replies[0]["payload"]["scanAvailable"])

  def test_scan_result_is_correlated_and_never_claims_a_verdict(self):
    run = self.run_host(
      frame(handshake()) +
      frame(scan_request("scan_1")) +
      frame(scan_status("status_1", "scan_1")) +
      frame(scan_result("result_1", "scan_1"))
    )
    self.assertEqual(run.returncode, 0)
    self.assert_diagnostics(run)
    replies = responses(run.stdout)
    self.assertEqual(len(replies), 4)
    self.assert_handshake_response(replies[0])
    self.assertEqual(replies[1], unavailable_scan_reply())
    self.assertEqual(replies[2], unavailable_status_reply())
    self.assertEqual(replies[3], unavailable_result_reply())
    result = replies[3]["payload"]
    self.assertIsNone(result["result"])
    self.assertIs(result["scanCompleted"], False)
    self.assertIs(result["scanVerified"], False)
    self.assertIs(result["authorizesOpen"], False)
    for forbidden in ("detectionNames", "verdict", "path", "downloadId",
                      "percentComplete", "clean", "scanAvailable"):
      self.assertNotIn(forbidden, result)

  def test_scan_result_unknown_repeated_and_new_connections_stay_unavailable(self):
    requests = [handshake(), scan_result("unknown_1", "missing"),
                scan_request("manual_1"), scan_result("known_1", "manual_1"),
                ping("still_alive"), scan_result("unknown_2", "missing")]
    run = self.run_host(b"".join(frame(m) for m in requests))
    self.assertEqual(run.returncode, 0)
    self.assert_diagnostics(run)
    replies = responses(run.stdout)
    self.assertEqual(len(replies), len(requests))
    self.assert_handshake_response(replies[0])
    self.assertEqual(replies[1], unavailable_result_reply("unknown_1", "missing"))
    self.assertEqual(replies[2], unavailable_scan_reply("manual_1"))
    self.assertEqual(replies[3], unavailable_result_reply("known_1", "manual_1"))
    self.assertEqual(replies[4]["topic"], "host.ping")
    self.assertEqual(replies[5], unavailable_result_reply("unknown_2", "missing"))

    fresh = self.run_host(frame(handshake()) +
                          frame(scan_result("fresh_1", "manual_1")))
    self.assertEqual(fresh.returncode, 0)
    self.assert_diagnostics(fresh)
    self.assertEqual(responses(fresh.stdout)[1],
                     unavailable_result_reply("fresh_1", "manual_1"))

  def test_scan_result_rejects_invalid_ids_and_caller_verdicts(self):
    valid = scan_result()
    malformed = [
      dict(valid, payload=None),
      dict(valid, payload={}),
      dict(valid, payload=[]),
      dict(valid, payload={"scanRequestId": ""}),
      dict(valid, payload={"scanRequestId": "x" * 81}),
      dict(valid, payload={"scanRequestId": "has space"}),
      dict(valid, payload={"scanRequestId": "../private.pdf"}),
      dict(valid, payload={"scanRequestId": 1}),
      dict(valid, payload={"scanRequestId": True}),
      dict(valid, payload={"scanRequestId": None}),
      dict(valid, payload={"scanRequestId": ["scan_1"]}),
      dict(valid, payload={"scanRequestId": "scan_1", "result": "clean"}),
      dict(valid, payload={"scanRequestId": "scan_1", "status": "clean"}),
      dict(valid, payload={"scanRequestId": "scan_1", "scanVerified": True}),
      dict(valid, payload={"scanRequestId": "scan_1", "authorizesOpen": True}),
      dict(valid, payload={"scanRequestId": "scan_1", "path": "/tmp/private.pdf"}),
      dict(valid, payload={"scanRequestId": "scan_1", "protectionLevel": "off"}),
      dict(valid, kind="event"),
      dict(valid, kind="response"),
      dict(valid, version=2),
      dict(valid, requestId="bad/id"),
      dict(valid, topic="pdf.result"),
    ]
    for message in malformed:
      with self.subTest(message=message):
        run = self.run_host(frame(handshake()) + frame(message))
        self.assertNotEqual(run.returncode, 0)
        self.assert_diagnostics(run)
        replies = responses(run.stdout)
        self.assertEqual(len(replies), 1)
        self.assert_handshake_response(replies[0])

  def test_scan_result_does_not_access_a_local_pdf_or_open_a_file(self):
    with tempfile.TemporaryDirectory(prefix="native-result-no-action-") as d:
      private_file = Path(d) / "private.pdf"
      original = b"private file bytes cannot be inferred from a scan result"
      private_file.write_bytes(original)
      malformed = dict(scan_result(), payload={"scanRequestId": "scan_1",
                                                 "path": str(private_file)})
      refused = self.run_host(frame(handshake()) + frame(malformed))
      self.assertNotEqual(refused.returncode, 0)
      self.assert_diagnostics(refused)
      self.assertNotIn(str(private_file).encode(), refused.stdout)
      self.assertNotIn(original, refused.stdout)
      self.assertEqual(private_file.read_bytes(), original)

      run = self.run_host(frame(handshake()) + frame(scan_result()))
      self.assertEqual(run.returncode, 0)
      self.assert_diagnostics(run)
      self.assertEqual(responses(run.stdout)[1], unavailable_result_reply())
      self.assertEqual(private_file.read_bytes(), original)

  def test_scan_cancel_requires_completed_handshake(self):
    for prefix in (b"", frame(ping("probe"))):
      with self.subTest(probe=bool(prefix)):
        run = self.run_host(prefix + frame(scan_cancel()))
        self.assertNotEqual(run.returncode, 0)
        self.assert_diagnostics(run)
        replies = responses(run.stdout)
        self.assertEqual(len(replies), 1 if prefix else 0)
        if replies:
          self.assertEqual(replies[0]["topic"], "host.ping")
          self.assertIs(replies[0]["payload"]["scanAvailable"], False)

  def test_scan_cancel_correlates_and_never_claims_a_cancellation(self):
    run = self.run_host(
      frame(handshake()) +
      frame(scan_request("scan_1")) +
      frame(scan_cancel("cancel_1", "scan_1"))
    )
    self.assertEqual(run.returncode, 0)
    self.assert_diagnostics(run)
    replies = responses(run.stdout)
    self.assertEqual(len(replies), 3)
    self.assert_handshake_response(replies[0])
    self.assertEqual(replies[1], unavailable_scan_reply())
    self.assertEqual(replies[2], unavailable_cancel_reply())
    payload = replies[2]["payload"]
    self.assertIs(payload["cancellationAccepted"], False)
    self.assertIs(payload["cancelled"], False)
    self.assertIs(payload["scanStarted"], False)
    self.assertIs(payload["scanVerified"], False)
    self.assertIs(payload["authorizesOpen"], False)
    for forbidden in ("pid", "processId", "path", "verdict", "result",
                      "signal", "scanCompleted"):
      self.assertNotIn(forbidden, payload)

  def test_scan_cancel_unknown_repeat_and_reconnection_remain_unavailable(self):
    messages = [handshake(), scan_cancel("unknown_1", "missing"),
                scan_request("manual_1"), scan_cancel("cancel_1", "manual_1"),
                scan_cancel("cancel_2", "manual_1"),
                scan_status("status_1", "manual_1"),
                scan_result("result_1", "manual_1"), ping("still_alive")]
    run = self.run_host(b"".join(frame(m) for m in messages))
    self.assertEqual(run.returncode, 0)
    self.assert_diagnostics(run)
    replies = responses(run.stdout)
    self.assertEqual(len(replies), len(messages))
    self.assert_handshake_response(replies[0])
    self.assertEqual(replies[1], unavailable_cancel_reply("unknown_1", "missing"))
    self.assertEqual(replies[2], unavailable_scan_reply("manual_1"))
    self.assertEqual(replies[3], unavailable_cancel_reply("cancel_1", "manual_1"))
    self.assertEqual(replies[4], unavailable_cancel_reply("cancel_2", "manual_1"))
    self.assertEqual(replies[5], unavailable_status_reply("status_1", "manual_1"))
    self.assertEqual(replies[6], unavailable_result_reply("result_1", "manual_1"))
    self.assertEqual(replies[7]["topic"], "host.ping")

    fresh = self.run_host(frame(handshake()) +
                          frame(scan_cancel("fresh_1", "manual_1")))
    self.assertEqual(fresh.returncode, 0)
    self.assert_diagnostics(fresh)
    self.assertEqual(responses(fresh.stdout)[1],
                     unavailable_cancel_reply("fresh_1", "manual_1"))

  def test_scan_cancel_rejects_malformed_and_privileged_payloads(self):
    valid = scan_cancel()
    malformed = [
      dict(valid, payload=None),
      dict(valid, payload={}),
      dict(valid, payload=[]),
      dict(valid, payload={"scanRequestId": ""}),
      dict(valid, payload={"scanRequestId": "x" * 81}),
      dict(valid, payload={"scanRequestId": "has space"}),
      dict(valid, payload={"scanRequestId": "../private.pdf"}),
      dict(valid, payload={"scanRequestId": 1}),
      dict(valid, payload={"scanRequestId": True}),
      dict(valid, payload={"scanRequestId": None}),
      dict(valid, payload={"scanRequestId": ["scan_1"]}),
      dict(valid, payload={"scanRequestId": "scan_1", "pid": 12345}),
      dict(valid, payload={"scanRequestId": "scan_1", "signal": "SIGKILL"}),
      dict(valid, payload={"scanRequestId": "scan_1", "path": "/tmp/private.pdf"}),
      dict(valid, payload={"scanRequestId": "scan_1", "cancelled": True}),
      dict(valid, payload={"scanRequestId": "scan_1", "authorizesOpen": True}),
      dict(valid, payload={"scanRequestId": "scan_1", "scanVerified": True}),
      dict(valid, payload={"scanRequestId": "scan_1", "protectionLevel": "off"}),
      dict(valid, kind="response"),
      dict(valid, kind="event"),
      dict(valid, version=2),
      dict(valid, requestId="bad/id"),
      dict(valid, topic="pdf.cancel"),
    ]
    for message in malformed:
      with self.subTest(message=message):
        run = self.run_host(frame(handshake()) + frame(message))
        self.assertNotEqual(run.returncode, 0)
        self.assert_diagnostics(run)
        replies = responses(run.stdout)
        self.assertEqual(len(replies), 1)
        self.assert_handshake_response(replies[0])

  def test_scan_cancel_never_reads_a_file_or_terminates_a_process(self):
    with tempfile.TemporaryDirectory(prefix="native-cancel-no-action-") as d:
      private_file = Path(d) / "private.pdf"
      original = b"cancellation must not read or overwrite private PDF contents"
      private_file.write_bytes(original)
      invalid = dict(scan_cancel(), payload={
        "scanRequestId": "scan_1", "path": str(private_file),
        "pid": os.getpid(), "signal": "SIGTERM"
      })
      refused = self.run_host(frame(handshake()) + frame(invalid))
      self.assertNotEqual(refused.returncode, 0)
      self.assert_diagnostics(refused)
      self.assertNotIn(str(private_file).encode(), refused.stdout)
      self.assertNotIn(original, refused.stdout)
      self.assertEqual(private_file.read_bytes(), original)

      accepted = self.run_host(frame(handshake()) + frame(scan_cancel()))
      self.assertEqual(accepted.returncode, 0)
      self.assert_diagnostics(accepted)
      self.assertEqual(responses(accepted.stdout)[1], unavailable_cancel_reply())
      self.assertEqual(private_file.read_bytes(), original)

  def test_partial_headers_and_bodies_expire_without_a_response(self):
    # Keep stdin open: EOF would otherwise test truncation, not a deadline.
    stalled = [b"\x01", struct.pack("<I", 50) + b"{}"]
    for index, fragment in enumerate(stalled):
      with self.subTest(fragment=index):
        with subprocess.Popen([str(self.binary)], stdin=subprocess.PIPE,
                              stdout=subprocess.PIPE, stderr=subprocess.PIPE) as process:
          process.stdin.write(frame(ping("before")) + fragment)
          process.stdin.flush()
          started = time.monotonic()
          self.assertNotEqual(process.wait(timeout=8), 0)
          self.assertGreaterEqual(time.monotonic() - started, 3.5)
          self.assertEqual(process.stderr.read(), b"")
          self.assertEqual([r["requestId"] for r in responses(process.stdout.read())],
                           ["before"])
          process.stdin.close()

  def test_idle_native_connection_expires_without_protocol_output(self):
    # A browser that never sends a request must not retain an idle host forever.
    with subprocess.Popen([str(self.binary)], stdin=subprocess.PIPE,
                          stdout=subprocess.PIPE, stderr=subprocess.PIPE) as process:
      started = time.monotonic()
      self.assertNotEqual(process.wait(timeout=13), 0)
      self.assertGreaterEqual(time.monotonic() - started, 8.5)
      self.assertEqual(process.stdout.read(), b"")
      self.assertEqual(process.stderr.read(), b"")
      process.stdin.close()

  def test_slow_but_complete_frame_and_clean_eof_remain_valid(self):
    with subprocess.Popen([str(self.binary)], stdin=subprocess.PIPE,
                          stdout=subprocess.PIPE, stderr=subprocess.PIPE) as process:
      request = frame(ping("chunked"))
      for part in (request[:1], request[1:3], request[3:7], request[7:]):
        process.stdin.write(part)
        process.stdin.flush()
        time.sleep(0.03)
      process.stdin.close()
      process.stdin = None
      output, errors = process.communicate(timeout=6)
      self.assertEqual(process.returncode, 0)
      self.assertEqual(errors, b"")
      self.assertEqual(responses(output)[0]["requestId"], "chunked")

  def test_blocked_response_pipe_expires_without_diagnostics(self):
    # Regular-file stdin avoids deadlocking the test writer. The host's
    # stdout pipe is deliberately never drained until its write deadline.
    message = frame(ping("fill"))
    with tempfile.TemporaryFile() as requests:
      requests.write(message * 4096)
      requests.seek(0)
      with subprocess.Popen([str(self.binary)], stdin=requests,
                            stdout=subprocess.PIPE, stderr=subprocess.PIPE) as process:
        self.assertNotEqual(process.wait(timeout=8), 0)
        output = process.stdout.read()
        self.assertGreater(len(output), 4)
        self.assertEqual(process.stderr.read(), b"")

  def test_diagnostics_are_isolated_from_framed_protocol_output(self):
    private_path = "/private/Sensitive-Document-12345.pdf"
    invalid = dict(ping("bad"), payload={
      "path": private_path, "diagnostic": "DO_NOT_ECHO_THIS_VALUE"
    })
    result = self.run_host(frame(ping("valid")) + frame(invalid))
    self.assertNotEqual(result.returncode, 0)
    self.assertEqual(responses(result.stdout), [{
      "version": 1, "kind": "response", "topic": "host.ping",
      "requestId": "valid", "payload": {
        "scanAvailable": False, "status": "transport-only"
      }
    }])
    self.assertEqual(result.stderr, b"pdf-magic-native-host: invalid-message\n")
    for secret in (private_path.encode(), b"DO_NOT_ECHO_THIS_VALUE", b"bad"):
      self.assertNotIn(secret, result.stdout + result.stderr)

  def test_error_channel_differentiates_invalid_frames_from_messages(self):
    cases = [
      (b"\\x01", b"pdf-magic-native-host: invalid-frame\n"),
      (struct.pack("<I", 16385), b"pdf-magic-native-host: invalid-frame\n"),
      (struct.pack("<I", 8) + b"{}", b"pdf-magic-native-host: invalid-frame\n"),
      (struct.pack("<I", 8) + b"not json", b"pdf-magic-native-host: invalid-message\n"),
      (frame(dict(ping(), version=2)), b"pdf-magic-native-host: invalid-message\n")
    ]
    for data, diagnostic in cases:
      with self.subTest(diagnostic=diagnostic, data=data):
        result = self.run_host(data)
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(result.stdout, b"")
        self.assertEqual(result.stderr, diagnostic)

  def test_extension_stream_disconnect_during_scan_request(self):
    # The standalone host cannot start scanning: an extension closing its
    # native messaging pipe must terminate the connection without inventing
    # an active scan, a verdict, or permission to open a document.
    submitted = frame(handshake()) + frame(scan_request("inflight_1"))
    run = self.run_host(submitted)
    self.assertEqual(run.returncode, 0)
    self.assert_diagnostics(run)
    replies = responses(run.stdout)
    self.assertEqual(len(replies), 2)
    self.assert_handshake_response(replies[0])
    self.assertEqual(replies[1], unavailable_scan_reply("inflight_1"))

    # A new process cannot inherit a handshake or any scan job identity.
    fresh = self.run_host(frame(scan_status("late_1", "inflight_1")))
    self.assertNotEqual(fresh.returncode, 0)
    self.assertEqual(fresh.stdout, b"")
    self.assert_diagnostics(fresh)

  def test_extension_disconnection_mid_frame_fails_closed(self):
    # Broken native messaging streams must not produce partial responses,
    # stderr path leaks, or any scanner result after the last complete frame.
    partial = frame(scan_result("late_1", "inflight_1"))[:-3]
    run = self.run_host(frame(handshake()) + frame(scan_request("inflight_1")) +
                        partial)
    self.assertNotEqual(run.returncode, 0)
    self.assert_diagnostics(run)
    replies = responses(run.stdout)
    self.assertEqual(len(replies), 2)
    self.assert_handshake_response(replies[0])
    self.assertEqual(replies[1], unavailable_scan_reply("inflight_1"))

  def test_truncated_and_invalid_length_fail_closed(self):
    for data in (b"\x01", b"\x08\x00\x00\x00{}",
                 struct.pack("<I", 0), struct.pack("<I", 16385),
                 struct.pack("<I", 0xffffffff)):
      with self.subTest(data=data):
        result = self.run_host(data)
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(result.stdout, b"")
        self.assert_diagnostics(result)

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
        self.assert_diagnostics(result)

    # Preserve the exact JSON tokens: Python otherwise normalizes exponent forms.
    encoded = json.dumps(ping(), separators=(",", ":")).encode("utf-8")
    self.assertIn(b'"version":1', encoded)
    for literal in (b"1e0", b"1E+0", b"1.0000000000000001"):
      with self.subTest(literal=literal):
        body = encoded.replace(b'"version":1', b'"version":' + literal, 1)
        result = self.run_host(struct.pack("<I", len(body)) + body)
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(result.stdout, b"")
        self.assert_diagnostics(result)

  def test_browser_supplied_origin_does_not_enable_a_scan(self):
    result = self.run_host(frame(ping()), "chrome-extension://exampleid/")
    self.assertEqual(result.returncode, 0)
    reply, = responses(result.stdout)
    self.assertFalse(reply["payload"]["scanAvailable"])

  def test_messages_cannot_launch_an_executable(self):
    # Exercise the compiled binary, not a mocked JSON validator. An attacker
    # controls messages, but cannot select a program or its arguments.
    with tempfile.TemporaryDirectory(prefix="native-no-exec-") as directory:
      launcher = Path(directory) / "attacker-command"
      marker = Path(directory) / "launched"
      launcher.write_text("#!/bin/sh\nprintf executed > '" + str(marker) + "'\n",
                          encoding="utf-8")
      launcher.chmod(0o700)
      command = str(launcher)
      attempts = [
        dict(ping("exec_1"), topic="host.exec",
             payload={"executable": command, "args": [str(marker)]}),
        dict(ping("exec_2"), topic="process.launch",
             payload={"command": command}),
        dict(ping("exec_3"), topic="shell.run",
             payload={"shell": "/bin/sh", "script": command}),
        dict(ping("exec_4"), topic="scan.execute",
             payload={"binary": command}),
        dict(ping("exec_5"), topic="pdf.open",
             payload={"application": command}),
        dict(ping("exec_6"), topic="host.run",
             payload={"path": command}),
        dict(ping("exec_7"), topic="host.ping",
             payload={"command": command}),
        dict(health("exec_8"), payload={"executable": command}),
        dict(scan_request("exec_9"), payload={
          "intent": "user-selected-pdf", "executable": command}),
        dict(scan_status("exec_10"), payload={
          "scanRequestId": "scan_1", "command": command}),
        dict(scan_result("exec_11"), payload={
          "scanRequestId": "scan_1", "argv": [command]}),
        dict(scan_cancel("exec_12"), payload={
          "scanRequestId": "scan_1", "pid": os.getpid(), "signal": "SIGTERM",
          "executable": command}),
        dict(ping("exec_13"), topic="host.handshake", payload={
          "clientNonce": "Client_Challenge_123456789", "command": command}),
      ]
      for message in attempts:
        with self.subTest(topic=message["topic"], request=message["requestId"]):
          run = self.run_host(frame(handshake()) + frame(message))
          self.assertNotEqual(run.returncode, 0)
          self.assert_diagnostics(run)
          received = responses(run.stdout)
          self.assertEqual(len(received), 1)
          self.assert_handshake_response(received[0])
          self.assertFalse(marker.exists())

      # A failed command attempt cannot poison another native process.
      recovery = self.run_host(frame(handshake()) + frame(scan_request()))
      self.assertEqual(recovery.returncode, 0)
      self.assert_diagnostics(recovery)
      self.assertEqual(responses(recovery.stdout)[1], unavailable_scan_reply())
      self.assertFalse(marker.exists())

  def test_native_host_forbids_process_launch_apis(self):
    # Guard the transport-only source against accidental execution primitives.
    import re
    source = SOURCE.read_text(encoding="utf-8")
    for forbidden in (
      r"\bProcess\s*\(", r"\bNSTask\b", r"\bposix_spawn(?:p)?\s*\(",
      r"\bexec(?:l|le|lp|v|ve|vp|vpe)?\s*\(", r"\bsystem\s*\(",
      r"\bpopen\s*\(", r"\bfork\s*\(", r"\bNSWorkspace\b",
      r"\bdlopen\s*\("
    ):
      with self.subTest(forbidden=forbidden):
        self.assertIsNone(re.search(forbidden, source))

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
