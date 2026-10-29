"""Find PDF rich-media content and asset references without executing media.

Optional, fail-closed Enhanced inspection. Unlike the pre-existing annotation
subtype classifier, this checks the referenced /RichMediaContent dictionaries,
configurations and asset name trees, including otherwise orphaned PDF objects.
No media stream is decoded and no external target is fetched or opened.
"""

from dataclasses import dataclass
from io import BytesIO

MAX_PDF_BYTES = 16 * 1024 * 1024
MAX_PAGES = 1024
MAX_INDIRECT_OBJECTS = 4096
MAX_GRAPH_NODES = 65536
MAX_MEDIA_ENTRIES = 512
MAX_ASSET_TREE_NODES = 256
BLOCK_MESSAGE = "PDF rich-media content could not be fully inspected; opening was stopped."


class PDFRichMediaInspectionError(RuntimeError):
  """Untrusted or unsupported rich media is never a clean verdict."""


@dataclass(frozen=True)
class PDFRichMediaInspection:
  annotation_count: int
  content_count: int
  configuration_count: int
  asset_reference_count: int
  permits_open: bool = False

  def __post_init__(self):
    values = (self.annotation_count, self.content_count,
              self.configuration_count, self.asset_reference_count)
    if (any(type(v) is not int or not 0 <= v <= MAX_MEDIA_ENTRIES
            for v in values) or self.permits_open is not False):
      raise ValueError("Rich-media evidence cannot authorize opening")

  @property
  def has_rich_media(self):
    return bool(self.annotation_count or self.content_count or
                self.configuration_count or self.asset_reference_count)


def inspect_pdf_rich_media(contents: bytes) -> PDFRichMediaInspection:
  """Recognize /RichMedia and /RichMediaContent with bounded indirect traversal.

  Inspect only dictionaries and file specifications. Media assets, scripts,
  renditions and activation commands are never followed, decoded or executed.
  Any malformed reference, resource exhaustion or unsupported object stream
  stops the inspection rather than implying absence of rich-media content.
  """
  if (type(contents) is not bytes or not 0 < len(contents) <= MAX_PDF_BYTES or
      not contents.startswith(b"%PDF-") or
      not contents.rstrip().endswith(b"%%EOF")):
    raise PDFRichMediaInspectionError(BLOCK_MESSAGE)

  try:
    from pypdf import PdfReader
    from pypdf.generic import (
      ArrayObject, ByteStringObject, DictionaryObject, IndirectObject,
      NameObject, TextStringObject,
    )
  except (ImportError, OSError):
    raise PDFRichMediaInspectionError(BLOCK_MESSAGE) from None

  try:
    reader = PdfReader(BytesIO(contents), strict=True)
    if reader.is_encrypted or reader.xref_objStm or len(reader.pages) > MAX_PAGES:
      raise PDFRichMediaInspectionError(BLOCK_MESSAGE)

    roots = [reader.trailer]
    indexed = 0
    for generation, offsets in reader.xref.items():
      if type(generation) is not int or not 0 <= generation <= 65535:
        raise PDFRichMediaInspectionError(BLOCK_MESSAGE)
      for number, offset in offsets.items():
        if number == 0:
          continue
        if (type(number) is not int or type(offset) is not int or
            number < 1 or offset <= 0):
          raise PDFRichMediaInspectionError(BLOCK_MESSAGE)
        indexed += 1
        if indexed > MAX_INDIRECT_OBJECTS:
          raise PDFRichMediaInspectionError(BLOCK_MESSAGE)
        roots.append(IndirectObject(number, generation, reader))

    cache = {}
    seen_nodes = set()
    annotations = set()
    contents_seen = set()
    configs_seen = set()
    assets_seen = set()
    count_assets = 0
    visited_nodes = 0

    def resolve(value):
      chain = set()
      while isinstance(value, IndirectObject):
        key = (value.idnum, value.generation)
        if key in chain:
          raise PDFRichMediaInspectionError(BLOCK_MESSAGE)
        chain.add(key)
        if key not in cache:
          if len(cache) >= MAX_INDIRECT_OBJECTS:
            raise PDFRichMediaInspectionError(BLOCK_MESSAGE)
          cache[key] = value.get_object()
        value = cache[key]
        if value is None:
          raise PDFRichMediaInspectionError(BLOCK_MESSAGE)
      return value

    def dictionary(value):
      obj = resolve(value)
      if not isinstance(obj, DictionaryObject):
        raise PDFRichMediaInspectionError(BLOCK_MESSAGE)
      return obj

    def count_configuration(value):
      obj = dictionary(value)
      configs_seen.add(id(obj))
      if len(configs_seen) > MAX_MEDIA_ENTRIES:
        raise PDFRichMediaInspectionError(BLOCK_MESSAGE)
      if "/Instances" in obj:
        instances = resolve(obj.raw_get("/Instances"))
        if not isinstance(instances, ArrayObject) or len(instances) > MAX_MEDIA_ENTRIES:
          raise PDFRichMediaInspectionError(BLOCK_MESSAGE)
        for instance in instances:
          dictionary(instance)

    def count_assets_tree(value):
      nonlocal count_assets
      pending = [value]
      while pending:
        tree = dictionary(pending.pop())
        marker = id(tree)
        if marker in assets_seen:
          raise PDFRichMediaInspectionError(BLOCK_MESSAGE)
        assets_seen.add(marker)
        if len(assets_seen) > MAX_ASSET_TREE_NODES:
          raise PDFRichMediaInspectionError(BLOCK_MESSAGE)
        if "/Names" in tree:
          entries = resolve(tree.raw_get("/Names"))
          if not isinstance(entries, ArrayObject) or len(entries) % 2:
            raise PDFRichMediaInspectionError(BLOCK_MESSAGE)
          for i in range(0, len(entries), 2):
            name = resolve(entries[i])
            if not isinstance(name, (TextStringObject, ByteStringObject)):
              raise PDFRichMediaInspectionError(BLOCK_MESSAGE)
            spec = dictionary(entries[i + 1])
            if (spec.get("/Type") not in (None, "/Filespec") or
                not any(key in spec for key in ("/F", "/UF", "/EF"))):
              raise PDFRichMediaInspectionError(BLOCK_MESSAGE)
            count_assets += 1
            if count_assets > MAX_MEDIA_ENTRIES:
              raise PDFRichMediaInspectionError(BLOCK_MESSAGE)
        if "/Kids" in tree:
          kids = resolve(tree.raw_get("/Kids"))
          if not isinstance(kids, ArrayObject) or len(kids) > MAX_ASSET_TREE_NODES:
            raise PDFRichMediaInspectionError(BLOCK_MESSAGE)
          pending.extend(kids)
        if "/Names" not in tree and "/Kids" not in tree:
          raise PDFRichMediaInspectionError(BLOCK_MESSAGE)

    stack = roots
    while stack:
      node = resolve(stack.pop())
      visited_nodes += 1
      if visited_nodes > MAX_GRAPH_NODES:
        raise PDFRichMediaInspectionError(BLOCK_MESSAGE)
      if not isinstance(node, (DictionaryObject, ArrayObject)):
        continue
      marker = id(node)
      if marker in seen_nodes:
        continue
      seen_nodes.add(marker)
      if isinstance(node, ArrayObject):
        stack.extend(node)
        continue

      if node.get("/Subtype") == "/RichMedia":
        annotations.add(marker)
        if len(annotations) > MAX_MEDIA_ENTRIES:
          raise PDFRichMediaInspectionError(BLOCK_MESSAGE)
        if "/RichMediaContent" not in node:
          raise PDFRichMediaInspectionError(BLOCK_MESSAGE)

      if ("/RichMediaContent" in node or
          node.get("/Type") == "/RichMediaContent"):
        content = (dictionary(node.raw_get("/RichMediaContent"))
                   if "/RichMediaContent" in node else node)
        content_id = id(content)
        if content_id not in contents_seen:
          contents_seen.add(content_id)
          if len(contents_seen) > MAX_MEDIA_ENTRIES:
            raise PDFRichMediaInspectionError(BLOCK_MESSAGE)
          if "/Configurations" in content:
            configurations = resolve(content.raw_get("/Configurations"))
            if (not isinstance(configurations, ArrayObject) or
                len(configurations) > MAX_MEDIA_ENTRIES):
              raise PDFRichMediaInspectionError(BLOCK_MESSAGE)
            for config in configurations:
              count_configuration(config)
          if "/Assets" in content:
            count_assets_tree(content.raw_get("/Assets"))

      if node.get("/Type") == "/RichMediaConfiguration":
        count_configuration(node)

      # Referenced /RichMediaSettings dictionaries can have activation hooks.
      # The exact syntax is checked here, but no activation is performed.
      if "/RichMediaSettings" in node:
        dictionary(node.raw_get("/RichMediaSettings"))

      stack.extend(node.raw_get(key) for key in node.keys())

    return PDFRichMediaInspection(
      len(annotations), len(contents_seen), len(configs_seen), count_assets
    )
  except PDFRichMediaInspectionError:
    raise
  except Exception:
    # Suppress parser diagnostics containing private text or embedded filenames.
    raise PDFRichMediaInspectionError(BLOCK_MESSAGE) from None
