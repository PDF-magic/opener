"""Strict JSON v1 envelope for a future local native messaging host.

Pure data codec only: no native host, transport, permissions, scan or launch.
"""
import json
import math
import re

MESSAGE_VERSION = 1
MAX_MESSAGE_BYTES = 16 * 1024
_MAX_DEPTH = 8
_MAX_NODES = 512
_MAX_ITEMS = 256
_MAX_STRING = 8192
_MAX_SAFE_INTEGER = 2**53 - 1
_FIELDS = frozenset({"version", "kind", "topic", "requestId", "payload"})
_KINDS = frozenset({"request", "response", "event"})
_UNSAFE_KEYS = frozenset({"__proto__", "constructor", "prototype"})
_TOPIC = re.compile(r"[a-z][a-z0-9]*(?:\.[a-z][a-z0-9]*)*", re.ASCII)
_REQUEST_ID = re.compile(r"[A-Za-z0-9_-]+", re.ASCII)


class InvalidNativeMessage(ValueError):
  """A generic, path-free failure."""


def _invalid():
  raise InvalidNativeMessage("Invalid native JSON message")


def _object_from_pairs(pairs):
  result = {}
  for key, value in pairs:
    if key in result or key in _UNSAFE_KEYS:
      _invalid()
    result[key] = value
  return result


def _invalid_constant(_value):
  _invalid()


def _validate_json(value, depth, budget):
  budget[0] += 1
  if budget[0] > _MAX_NODES or depth > _MAX_DEPTH:
    _invalid()
  if value is None or type(value) is bool:
    return
  if type(value) is str:
    if len(value) > _MAX_STRING:
      _invalid()
    try:
      value.encode("utf-8")
    except UnicodeEncodeError:
      _invalid()
    return
  if type(value) is int:
    if abs(value) > _MAX_SAFE_INTEGER:
      _invalid()
    return
  if type(value) is float:
    if not math.isfinite(value):
      _invalid()
    return
  if type(value) is list:
    if len(value) > _MAX_ITEMS:
      _invalid()
    for item in value:
      _validate_json(item, depth + 1, budget)
    return
  if type(value) is dict:
    if len(value) > _MAX_ITEMS:
      _invalid()
    for key, item in value.items():
      if type(key) is not str or key in _UNSAFE_KEYS:
        _invalid()
      _validate_json(item, depth + 1, budget)
    return
  _invalid()


def _validate_envelope(message):
  if type(message) is not dict or message.keys() != _FIELDS:
    _invalid()
  version = message["version"]
  kind = message["kind"]
  topic = message["topic"]
  request_id = message["requestId"]
  if type(version) is not int or version != MESSAGE_VERSION:
    _invalid()
  if type(kind) is not str or kind not in _KINDS:
    _invalid()
  if type(topic) is not str or len(topic) > 80 or not _TOPIC.fullmatch(topic):
    _invalid()
  if type(request_id) is not str or len(request_id) > 80 or not _REQUEST_ID.fullmatch(request_id):
    _invalid()
  _validate_json(message["payload"], 0, [0])


def encode_native_message(message):
  """Return UTF-8 JSON body bytes, without native transport framing."""
  try:
    _validate_envelope(message)
    encoded = json.dumps(message, ensure_ascii=False, allow_nan=False,
                         separators=(",", ":")).encode("utf-8")
    if len(encoded) > MAX_MESSAGE_BYTES:
      _invalid()
    return encoded
  except (RecursionError, UnicodeError, OverflowError, TypeError):
    _invalid()


def decode_native_message(data):
  """Parse exactly one UTF-8 JSON envelope, rejecting unsafe or ambiguous data."""
  if type(data) is not bytes or len(data) > MAX_MESSAGE_BYTES:
    _invalid()
  try:
    message = json.loads(data.decode("utf-8"),
                         object_pairs_hook=_object_from_pairs,
                         parse_constant=_invalid_constant)
    _validate_envelope(message)
    encode_native_message(message)
    return message
  except (UnicodeError, json.JSONDecodeError, RecursionError, TypeError, OverflowError):
    _invalid()
