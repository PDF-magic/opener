#!/usr/bin/env python3
"""Cross-layer native messaging protocol regression tests (no host registration)."""
import io
import json
from pathlib import Path
import struct
import subprocess
import unittest

from native_message_format import (
  InvalidNativeMessage, MAX_MESSAGE_BYTES, decode_native_message,
  encode_native_message,
)
from native_message_framing import (
  InvalidNativeFrame, MAX_FRAME_BYTES, read_native_frame, write_native_frame,
)

ROOT = Path(__file__).resolve().parents[2]


def envelope(kind="request", topic="host.ping", request_id="ping_1", payload=None):
  return {"version": 1, "kind": kind, "topic": topic,
          "requestId": request_id, "payload": payload}


class FragmentedInput:
  """Simulate a pipe that yields less than the requested byte count."""

  def __init__(self, data, chunk_size=2):
    self.input = io.BytesIO(data)
    self.chunk_size = chunk_size

  def read(self, count):
    return self.input.read(min(count, self.chunk_size))


class NativeMessagingProtocolTests(unittest.TestCase):
  def test_envelopes_survive_framing_and_fragmented_persistent_stream(self):
    messages = [
      envelope("request", "host.handshake", "hello_1", {
        "clientNonce": "Client_Challenge_123456789"}),
      envelope("response", "host.handshake", "hello_1", {
        "status": "transport-only", "scanAvailable": False}),
      envelope("event", "host.ping", "evt_1", {"label": "🦄"}),
    ]
    transport = io.BytesIO()
    for message in messages:
      body = encode_native_message(message)
      start = transport.tell()
      write_native_frame(transport, body)
      self.assertEqual(transport.getvalue()[start:start + 4],
                       struct.pack("<I", len(body)))
    reader = FragmentedInput(transport.getvalue())
    for message in messages:
      self.assertEqual(decode_native_message(read_native_frame(reader)), message)
    self.assertIsNone(read_native_frame(reader))

  def test_maximum_binary_frame_and_json_limits_are_independent(self):
    self.assertEqual(MAX_FRAME_BYTES, MAX_MESSAGE_BYTES)
    body = b"x" * MAX_FRAME_BYTES
    stream = io.BytesIO()
    write_native_frame(stream, body)
    self.assertEqual(read_native_frame(io.BytesIO(stream.getvalue())), body)
    with self.assertRaises(InvalidNativeMessage):
      decode_native_message(body)
    with self.assertRaises(InvalidNativeMessage):
      encode_native_message(envelope(payload="🦄" * 4200))

  def test_invalid_lengths_and_partial_frames_fail_before_json(self):
    for wire in (
      struct.pack("<I", 0),
      struct.pack("<I", MAX_FRAME_BYTES + 1) + b"not-a-pdf",
      b"\x01\x00",
      struct.pack("<I", 10) + b"short",
    ):
      with self.subTest(wire=wire[:4]):
        with self.assertRaises(InvalidNativeFrame):
          read_native_frame(FragmentedInput(wire, 1))
    self.assertIsNone(read_native_frame(io.BytesIO()))

  def test_complete_frame_does_not_make_invalid_json_acceptable(self):
    invalid_bodies = (
      b"not json",
      b'{"version":2,"kind":"request","topic":"host.ping","requestId":"x","payload":null}',
      b'{"version":1,"version":1,"kind":"request","topic":"host.ping","requestId":"x","payload":null}',
      b'{"version":1,"kind":"request","topic":"host.ping","requestId":"x","payload":{"__proto__":{}}}',
      b'{"version":1,"kind":"request","topic":"host.ping","requestId":"x","payload":null}trailing',
      b"\xff",
    )
    for body in invalid_bodies:
      with self.subTest(body=body[:30]):
        wire = io.BytesIO()
        write_native_frame(wire, body)
        framed = read_native_frame(io.BytesIO(wire.getvalue()))
        with self.assertRaises(InvalidNativeMessage):
          decode_native_message(framed)

  def test_encoded_body_must_not_be_mistaken_for_a_wire_frame(self):
    message = envelope(payload={"message": "valid data only"})
    body = encode_native_message(message)
    with self.assertRaises(InvalidNativeFrame):
      read_native_frame(io.BytesIO(body))
    wire = io.BytesIO()
    write_native_frame(wire, body)
    with self.assertRaises(InvalidNativeMessage):
      decode_native_message(wire.getvalue())
    self.assertEqual(decode_native_message(read_native_frame(
      io.BytesIO(wire.getvalue()))), message)

  def test_untrusted_scan_claims_remain_data_without_authority(self):
    # The codec and framing helpers must never create a scan or open action.
    message = envelope(topic="scan.request", payload={
      "scanVerified": True, "authorizesOpen": True,
      "path": "/private/not-accessed.pdf",
    })
    wire = io.BytesIO()
    write_native_frame(wire, encode_native_message(message))
    self.assertEqual(decode_native_message(read_native_frame(
      io.BytesIO(wire.getvalue()))), message)
    for name in ("native_message_framing.py", "native_message_format.py"):
      source = (ROOT / name).read_text(encoding="utf-8")
      for forbidden in ("subprocess.run(", "os.system(", "scan_and_open(",
                        "open_pdf(", "connectNative("):
        self.assertNotIn(forbidden, source)

  def test_webextension_codec_interoperates_over_framed_bytes(self):
    # Pass only an inert JSON envelope to the shared browser codec.
    request = envelope(payload={"unicode": "🦄", "nested": [None, True, 7]})
    wire = io.BytesIO()
    write_native_frame(wire, encode_native_message(request))
    body = read_native_frame(FragmentedInput(wire.getvalue(), 1))
    javascript = """
      import {parseMessage,serializeMessage} from "./extensions/webextension/src/messaging.js";
      const parts = [];
      for await (const part of process.stdin) parts.push(part);
      const incoming = Buffer.concat(parts).toString("utf8");
      process.stdout.write(serializeMessage(parseMessage(incoming)));
    """
    completed = subprocess.run(
      ["node", "--input-type=module", "-e", javascript],
      input=body, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
      cwd=ROOT, timeout=15, check=True,
    )
    response_wire = io.BytesIO()
    write_native_frame(response_wire, completed.stdout)
    self.assertEqual(decode_native_message(read_native_frame(
      FragmentedInput(response_wire.getvalue()))), request)


if __name__ == "__main__":
  unittest.main()
