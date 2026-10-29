"""Check declared PDF stream lengths against raw, indexed stream boundaries.

Read-only, bounded validation for the optional Enhanced structure parser.
No stream payload is decompressed, interpreted, logged, or executed. A clean
stream boundary is not a malware verdict or permission to open a document.
"""

from io import BytesIO
import re

MAX_STREAM_LENGTH_INPUT_BYTES = 16 * 1024 * 1024
MAX_INDEXED_STREAM_OBJECTS = 4096
MAX_STREAM_DICTIONARY_BYTES = 1024 * 1024
_FAILURE = "PDF stream length could not be verified; opening was stopped."
_OBJECT_HEADER = re.compile(rb"([0-9]+)[ \t\r\n]+([0-9]+)[ \t\r\n]+obj\b")
_STREAM_START = re.compile(rb"[ \t\r\n]*stream(?:\r\n|\n|\r)")
_STREAM_END = re.compile(rb"(?:\r\n|\n|\r)endstream(?=[\s%]|\Z)")
_FINAL_XREF = re.compile(rb"startxref[ \t\r\n]+([0-9]+)[ \t\r\n]+%%EOF[ \t\r\n]*\Z")


class PDFStreamLengthError(RuntimeError):
  """Fixed, content-free evidence that a stream cannot be trusted."""


def _dictionary_end(contents, start):
  """Find balanced dictionary closure, skipping strings, hex and comments.

  This is a delimiter scan only. The dictionary's actual types and indirect
  references are interpreted by the maintained pypdf object reader.
  """
  depth = 0
  literal = 0
  hex_string = False
  comment = False
  pos = start
  cap = min(len(contents), start + MAX_STREAM_DICTIONARY_BYTES)
  while pos < cap:
    ch = contents[pos]
    pair = contents[pos:pos + 2]
    if comment:
      if ch in (10, 13):
        comment = False
    elif hex_string:
      if ch == 62:
        hex_string = False
    elif literal:
      if ch == 92:
        pos += 1  # escaped delimiter or escaped end-of-line
      elif ch == 40:
        literal += 1
      elif ch == 41:
        literal -= 1
    elif ch == 37:
      comment = True
    elif ch == 40:
      literal = 1
    elif pair == b"<<":
      depth += 1
      pos += 1
    elif pair == b">>":
      depth -= 1
      pos += 1
      if depth == 0:
        return pos + 1
      if depth < 0:
        raise PDFStreamLengthError(_FAILURE)
    elif ch == 60:
      hex_string = True
    pos += 1
  raise PDFStreamLengthError(_FAILURE)


def _skip_layout(contents, offset):
  while offset < len(contents):
    ch = contents[offset]
    if ch in b" \t\r\n\x00\x0c":
      offset += 1
    elif ch == 37:  # PDF comment between object header and value
      offset += 1
      while offset < len(contents) and contents[offset] not in b"\r\n":
        offset += 1
    else:
      break
  return offset


def validate_pdf_stream_lengths(contents: bytes, reader) -> int:
  """Verify every indexed stream's /Length and physical endstream boundary.

  Include unreferenced traditional xref objects and the final xref-stream
  object, which some readers omit from their ordinary xref map. Compressed
  object-stream members cannot themselves be PDF stream objects. This check
  does not replace separate incremental-revision and ambiguity inspection.
  """
  if type(contents) is not bytes or not 0 < len(contents) <= MAX_STREAM_LENGTH_INPUT_BYTES:
    raise PDFStreamLengthError(_FAILURE)
  try:
    from pypdf.generic import DictionaryObject, IndirectObject, read_object

    entries = set()
    for generation, objects in reader.xref.items():
      for number, offset in objects.items():
        if number == 0:
          continue
        if not all(type(v) is int for v in (number, generation, offset)):
          raise PDFStreamLengthError(_FAILURE)
        entries.add((number, generation, offset))
        if len(entries) > MAX_INDEXED_STREAM_OBJECTS:
          raise PDFStreamLengthError(_FAILURE)

    trailer = _FINAL_XREF.search(contents[-2048:])
    if trailer is None:
      raise PDFStreamLengthError(_FAILURE)
    xref_offset = int(trailer.group(1))
    if not 0 < xref_offset < len(contents):
      raise PDFStreamLengthError(_FAILURE)
    xref_header = _OBJECT_HEADER.match(contents, xref_offset)
    if xref_header:
      entries.add((int(xref_header.group(1)), int(xref_header.group(2)), xref_offset))
    if len(entries) > MAX_INDEXED_STREAM_OBJECTS + 1:
      raise PDFStreamLengthError(_FAILURE)

    inspected = 0
    for number, generation, offset in sorted(entries, key=lambda item: item[2]):
      if not 0 < offset < len(contents):
        raise PDFStreamLengthError(_FAILURE)
      header = _OBJECT_HEADER.match(contents, offset)
      if (header is None or int(header.group(1)) != number
              or int(header.group(2)) != generation):
        raise PDFStreamLengthError(_FAILURE)
      beginning = _skip_layout(contents, header.end())
      if contents[beginning:beginning + 2] != b"<<":
        continue
      end = _dictionary_end(contents, beginning)
      marker = _STREAM_START.match(contents, end)
      if marker is None:
        # Not every dictionary with a /Length key is a stream.
        if re.match(rb"[ \t\r\n]*stream\b", contents[end:end + 80]):
          raise PDFStreamLengthError(_FAILURE)
        continue
      dictionary = read_object(BytesIO(contents[beginning:end]), reader)
      if not isinstance(dictionary, DictionaryObject):
        raise PDFStreamLengthError(_FAILURE)
      declared = dictionary.raw_get("/Length")
      if isinstance(declared, IndirectObject):
        declared = declared.get_object()
      if not isinstance(declared, int) or isinstance(declared, bool) or declared < 0:
        raise PDFStreamLengthError(_FAILURE)
      data_start = marker.end()
      boundary = data_start + declared
      if boundary > len(contents):
        raise PDFStreamLengthError(_FAILURE)
      if _STREAM_END.match(contents, boundary) is None:
        # Some valid streams count the final line ending as payload data.
        # Then endstream starts at the declared byte boundary, while the
        # required preceding EOL is included in the declared length.
        contained_eol = (
          boundary > data_start
          and contents[boundary - 1] in b"\r\n"
          and re.match(rb"endstream(?=[\s%]|\Z)", contents, boundary) is not None
        )
        if not contained_eol:
          raise PDFStreamLengthError(_FAILURE)
      inspected += 1
    return inspected
  except PDFStreamLengthError:
    raise
  except Exception:
    # Parser failures can contain private source text; never return it.
    raise PDFStreamLengthError(_FAILURE) from None
