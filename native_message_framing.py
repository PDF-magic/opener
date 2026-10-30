"""Bounded, transport-only WebExtensions native messaging stream framing.

Messages are byte strings, not trusted JSON or scanner verdicts. A separate
codec must validate every decoded body before any action can be considered.
"""
import struct

MAX_FRAME_BYTES = 16 * 1024
_PREFIX_BYTES = 4


class InvalidNativeFrame(ValueError):
  """Generic error for an invalid or incomplete native messaging frame."""


def _invalid():
  raise InvalidNativeFrame("Invalid native messaging frame")


def _read_exact(stream, count, *, allow_eof=False):
  chunks = []
  remaining = count
  while remaining:
    try:
      chunk = stream.read(remaining)
    except (OSError, ValueError, TypeError):
      _invalid()
    if type(chunk) is not bytes or len(chunk) > remaining:
      _invalid()
    if not chunk:
      if allow_eof and remaining == count:
        return None
      _invalid()
    chunks.append(chunk)
    remaining -= len(chunk)
  return b"".join(chunks)


def read_native_frame(stream):
  """Read one <uint32-le length><body> frame, or None at a clean EOF.

  Handles short binary reads and multiple messages on a persistent stream.
  A partial prefix or body, zero length or body over 16 KiB is rejected before
  attempting to parse JSON; no oversized allocation or stream scanning occurs.
  """
  prefix = _read_exact(stream, _PREFIX_BYTES, allow_eof=True)
  if prefix is None:
    return None
  (length,) = struct.unpack("<I", prefix)
  if not 0 < length <= MAX_FRAME_BYTES:
    _invalid()
  return _read_exact(stream, length)


def write_native_frame(stream, body):
  """Write one complete frame using short-write-aware binary stream writes.

  This framing helper does not validate JSON, authorize scan/open operations,
  write diagnostics to stdout, or change the user's preferences.
  """
  if type(body) is not bytes or not 0 < len(body) <= MAX_FRAME_BYTES:
    _invalid()
  frame = struct.pack("<I", len(body)) + body
  offset = 0
  while offset < len(frame):
    try:
      written = stream.write(frame[offset:])
    except (OSError, ValueError, TypeError):
      _invalid()
    if type(written) is not int or not 0 < written <= len(frame) - offset:
      _invalid()
    offset += written
  try:
    stream.flush()
  except (OSError, ValueError, TypeError, AttributeError):
    _invalid()
