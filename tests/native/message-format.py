"""Native JSON v1 security and JS interoperability regressions."""
import json
from pathlib import Path
import subprocess
import unittest

from native_message_format import (
  InvalidNativeMessage, MAX_MESSAGE_BYTES, MESSAGE_VERSION,
  decode_native_message, encode_native_message,
)

ROOT = Path(__file__).resolve().parent
SHARED_CODEC = ROOT / "extensions/webextension/src/messaging.js"


def sample(kind="request", payload=None):
  return {"version": MESSAGE_VERSION, "kind": kind, "topic": "example.ping",
          "requestId": "request_1", "payload": payload}


class NativeMessageFormatTests(unittest.TestCase):
  def test_v1_round_trip_for_each_kind(self):
    for kind in ("request", "response", "event"):
      message = sample(kind, {"nested": [None, True, 42, 1.25, "🦄"]})
      self.assertEqual(decode_native_message(encode_native_message(message)), message)
      self.assertEqual(set(message), {"version", "kind", "topic", "requestId", "payload"})

  def test_rejects_unknown_version_fields_and_types(self):
    for changes in (
      {"version": 0}, {"version": -1}, {"version": 2},
      {"version": 1.0}, {"version": "1"}, {"version": True},
      {"kind": "open"}, {"kind": 1}, {"topic": "bad/path"},
      {"topic": "bad..topic"}, {"topic": "A.ping"}, {"topic": "a" * 81},
      {"requestId": ""}, {"requestId": "path/secret"},
      {"requestId": "a" * 81}, {"extra": True},
    ):
      with self.subTest(changes=changes):
        with self.assertRaises(InvalidNativeMessage):
          encode_native_message(sample() | changes)
    with self.assertRaises(InvalidNativeMessage):
      encode_native_message({"version": 1})

  def test_rejects_unsupported_wire_version_representations(self):
    valid = encode_native_message(sample())
    self.assertIn(b'"version":1', valid)
    for literal in (b"0", b"-1", b"2", b"1.0", b"1e0", b"1E+0",
                    b"1.0000000000000001", b"true", b'"1"', b"null"):
      with self.subTest(version=literal):
        raw = valid.replace(b'"version":1', b'"version":' + literal, 1)
        with self.assertRaises(InvalidNativeMessage):
          decode_native_message(raw)

  def test_rejects_duplicate_keys_and_prototype_pollution(self):
    for wire in (
      b'{"version":1,"version":1,"kind":"request","topic":"a","requestId":"x","payload":null}',
      b'{"version":1,"kind":"event","topic":"a","requestId":"x","payload":{"__proto__":{}}}',
      b'{"version":1,"kind":"event","topic":"a","requestId":"x","payload":{"constructor":0}}',
    ):
      with self.assertRaises(InvalidNativeMessage):
        decode_native_message(wire)

  def test_fails_closed_on_non_json_nonfinite_and_untrusted_payloads(self):
    cyclic = []
    cyclic.append(cyclic)
    for value in (float("nan"), float("inf"), 2**53, {"constructor": "x"},
                  {"a": {1: "invalid key"}}, cyclic, object(), "\ud800"):
      with self.subTest(payload=type(value).__name__):
        with self.assertRaises(InvalidNativeMessage):
          encode_native_message(sample(payload=value))
    for data in (b'{', b'{}', b'null', b'[]', b'NaN', b'\xef\xbb\xbf{}',
                 b'{"version":1,"kind":"event","topic":"a","requestId":"x","payload":NaN}',
                 b'\xff', "not bytes", b' ' * (MAX_MESSAGE_BYTES + 1)):
      with self.assertRaises(InvalidNativeMessage):
        decode_native_message(data)

  def test_enforces_payload_depth_count_and_utf8_byte_limits(self):
    self.assertEqual(MAX_MESSAGE_BYTES, 16384)
    for payload in (list(range(257)), {str(i): i for i in range(257)},
                    "🦄" * 4100, {"value": "a" * 8193}):
      with self.assertRaises(InvalidNativeMessage):
        encode_native_message(sample(payload=payload))
    nested = {}
    for _ in range(10):
      nested = {"child": nested}
    with self.assertRaises(InvalidNativeMessage):
      encode_native_message(sample(payload=nested))
    with self.assertRaises(InvalidNativeMessage):
      encode_native_message(sample(payload=[[0] * 256, [1] * 256]))

  def test_messages_never_authorize_scanning_or_opening(self):
    for untrusted in ({"authorizesOpen": True}, {"scanVerified": True},
                      {"filePath": "/private/user.pdf"}):
      self.assertEqual(
        decode_native_message(encode_native_message(sample(payload=untrusted)))["payload"],
        untrusted
      )
    source = (ROOT / "native_message_format.py").read_text(encoding="utf-8")
    for forbidden in ("subprocess.run(", "os.system(", "scan_and_open(",
                      "open_pdf(", "sendNativeMessage(", "connectNative("):
      self.assertNotIn(forbidden, source)

  def test_shared_webextension_codec_interoperability(self):
    self.assertTrue(SHARED_CODEC.is_file())
    js = '''import {createMessage,parseMessage,serializeMessage} from "./extensions/webextension/src/messaging.js";
      const outgoing = createMessage("request","example.ping","request_1",{nested:[null,true,42,1.25,"🦄"]});
      const native = JSON.parse(process.argv[1]);
      if (JSON.stringify(parseMessage(native)) !== JSON.stringify(native)) process.exit(2);
      console.log(serializeMessage(outgoing));'''
    native_message = sample(payload={"nested": [None, True, 42, 1.25, "🦄"]})
    run = subprocess.run(["node", "--input-type=module", "-e", js,
                          json.dumps(native_message, ensure_ascii=False)],
                         cwd=ROOT, check=True, capture_output=True, text=True, timeout=15)
    self.assertEqual(decode_native_message(run.stdout.strip().encode("utf-8")), native_message)


if __name__ == "__main__":
  unittest.main()
