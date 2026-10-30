"""Portable, dependency-free regression tests for native host byte framing."""
import io
import struct
import unittest

from native_message_framing import (
  InvalidNativeFrame, MAX_FRAME_BYTES, read_native_frame, write_native_frame,
)


class ShortReader:
  def __init__(self, data, limit=1):
    self.source = io.BytesIO(data)
    self.limit = limit
    self.requests = []

  def read(self, count):
    self.requests.append(count)
    return self.source.read(min(count, self.limit))


class ShortWriter:
  def __init__(self, limit=1):
    self.output = bytearray()
    self.limit = limit
    self.flushes = 0

  def write(self, data):
    piece = data[:self.limit]
    self.output.extend(piece)
    return len(piece)

  def flush(self):
    self.flushes += 1


class NativeMessageFramingTests(unittest.TestCase):
  def test_little_endian_prefix_and_round_trip(self):
    for body in (b"{}", b"hello", b"\xf0\x9f\xa6\x84", b"x" * MAX_FRAME_BYTES):
      with self.subTest(size=len(body)):
        output = io.BytesIO()
        write_native_frame(output, body)
        wire = output.getvalue()
        self.assertEqual(wire[:4], struct.pack("<I", len(body)))
        self.assertEqual(len(wire), len(body) + 4)
        self.assertEqual(read_native_frame(io.BytesIO(wire)), body)

  def test_short_reads_reassemble_prefix_and_payload(self):
    body = b'{"version":1,"payload":null}'
    stream = ShortReader(struct.pack("<I", len(body)) + body)
    self.assertEqual(read_native_frame(stream), body)
    self.assertEqual(read_native_frame(stream), None)
    self.assertEqual(stream.requests[0], 4)
    self.assertTrue(all(0 < count <= len(body) for count in stream.requests))

  def test_multiple_frames_on_one_connection(self):
    output = io.BytesIO()
    for body in (b"one", b"two", b"three"):
      write_native_frame(output, body)
    stream = ShortReader(output.getvalue(), limit=2)
    self.assertEqual([read_native_frame(stream) for _ in range(3)],
                     [b"one", b"two", b"three"])
    self.assertIsNone(read_native_frame(stream))

  def test_empty_stream_is_clean_eof_but_truncation_is_invalid(self):
    self.assertIsNone(read_native_frame(io.BytesIO(b"")))
    for incomplete in (b"\x01", b"\x03\x00", b"\x03\x00\x00",
                       struct.pack("<I", 3), struct.pack("<I", 3) + b"a",
                       struct.pack("<I", 3) + b"ab"):
      with self.subTest(incomplete=incomplete):
        with self.assertRaisesRegex(InvalidNativeFrame, "^Invalid native messaging frame$"):
          read_native_frame(ShortReader(incomplete))

  def test_rejects_zero_and_oversized_length_before_reading_body(self):
    for length in (0, MAX_FRAME_BYTES + 1, 2**32 - 1):
      with self.subTest(length=length):
        stream = ShortReader(struct.pack("<I", length) + b"private-data", limit=4)
        with self.assertRaises(InvalidNativeFrame):
          read_native_frame(stream)
        self.assertEqual(stream.source.tell(), 4,
                         "never read or allocate an oversized body")

  def test_short_writes_retry_all_bytes_and_flush_once(self):
    body = b"payload"
    stream = ShortWriter()
    write_native_frame(stream, body)
    self.assertEqual(bytes(stream.output), struct.pack("<I", len(body)) + body)
    self.assertEqual(stream.flushes, 1)

  def test_rejects_invalid_output_without_writing(self):
    for body in (b"", b"a" * (MAX_FRAME_BYTES + 1), "text", bytearray(b"x"), None):
      stream = ShortWriter()
      with self.subTest(body_type=type(body).__name__):
        with self.assertRaises(InvalidNativeFrame):
          write_native_frame(stream, body)
        self.assertEqual(stream.output, b"")
        self.assertEqual(stream.flushes, 0)

  def test_rejects_stalled_or_malformed_streams(self):
    class BadReader:
      def read(self, count):
        return "not bytes"

    class BadWriter:
      def write(self, data):
        return None

      def flush(self):
        pass

    class StalledWriter(BadWriter):
      def write(self, data):
        return 0

    class OverwritingWriter(BadWriter):
      def write(self, data):
        return len(data) + 1

    with self.assertRaises(InvalidNativeFrame):
      read_native_frame(BadReader())
    for sink in (BadWriter(), StalledWriter(), OverwritingWriter()):
      with self.assertRaises(InvalidNativeFrame):
        write_native_frame(sink, b"data")

  def test_binary_body_is_transport_only_not_json_or_verdict(self):
    arbitrary_bytes = b"\x00\xff\x01not-json\x00"
    stream = io.BytesIO()
    write_native_frame(stream, arbitrary_bytes)
    self.assertEqual(read_native_frame(io.BytesIO(stream.getvalue())), arbitrary_bytes)


if __name__ == "__main__":
  unittest.main()
