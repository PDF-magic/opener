#!/usr/bin/env python3
"""Verify native window branding and complete macOS icon resource."""
from pathlib import Path
import struct
import unittest
import zlib

ROOT = Path(__file__).resolve().parents[2]
APP = ROOT / "PDFMagicOpenerApp" / "PDFMagicOpenerApp.swift"
PROJECT = ROOT / "PDFMagicOpener.xcodeproj" / "project.pbxproj"
INFO = ROOT / "PDFMagicOpenerApp" / "Info.plist"
ICON = ROOT / "PDFMagicOpenerApp" / "PDFMagicOpenerIcon.icns"
RESOLUTIONS = {b"icp4": 16, b"icp5": 32, b"icp6": 64,
               b"ic07": 128, b"ic08": 256, b"ic09": 512, b"ic10": 1024}


def check_png(data, size):
  assert data.startswith(b"\x89PNG\r\n\x1a\n")
  offset, chunks = 8, {}
  while offset < len(data):
    count = struct.unpack_from(">I", data, offset)[0]
    kind = data[offset + 4:offset + 8]
    end = offset + 8 + count
    assert end + 4 <= len(data), "Truncated PNG chunk"
    payload = data[offset + 8:end]
    assert zlib.crc32(kind + payload) == struct.unpack_from(">I", data, end)[0]
    chunks.setdefault(kind, []).append(payload)
    offset = end + 4
  assert offset == len(data)
  assert set(chunks) == {b"IHDR", b"PLTE", b"tRNS", b"IDAT", b"IEND"}
  assert struct.unpack(">IIBBBBB", chunks[b"IHDR"][0]) == (size, size, 8, 3, 0, 0, 0)
  assert chunks[b"tRNS"] == [b"\x00"]
  pixels = zlib.decompress(b"".join(chunks[b"IDAT"]))
  assert len(pixels) == size * (size + 1)
  assert all(pixels[y * (size + 1)] == 0 for y in range(size))
  assert len(set(pixels)) >= 5
  assert pixels[1] == 0, "Rounded-corner transparency is missing"


class NativeWindowBrandingTests(unittest.TestCase):
  def test_title_and_bundle_metadata_match(self):
    app = APP.read_text(encoding="utf-8")
    project = PROJECT.read_text(encoding="utf-8")
    self.assertIn('WindowGroup("PDF Magic Opener")', app)
    self.assertIn('Window("About PDF Magic Opener"', app)
    self.assertEqual(project.count('INFOPLIST_KEY_CFBundleDisplayName = "PDF Magic Opener";'), 2)
    self.assertEqual(project.count("INFOPLIST_KEY_CFBundleIconFile = PDFMagicOpenerIcon;"), 2)
    self.assertNotIn("CFBundleDocumentTypes", project)
    self.assertEqual(project.count("INFOPLIST_FILE = PDFMagicOpenerApp/Info.plist;"), 2)
    self.assertIn("<key>CFBundleIconFile</key>", INFO.read_text(encoding="utf-8"))

  def test_icon_is_in_the_built_app_resources(self):
    project = PROJECT.read_text(encoding="utf-8")
    for name in ("lastKnownFileType = image.icns;", "path = PDFMagicOpenerIcon.icns;",
                 "fileRef = A1000000000000000000001D;"):
      self.assertIn(name, project)
    # Other independently bundled resources may now share the build phase.
    resources = project.split("isa = PBXResourcesBuildPhase;", 1)[1].split(
        "runOnlyForDeploymentPostprocessing", 1)[0]
    self.assertIn("A10000000000000000000018,", resources)
    self.assertIn("A1000000000000000000001C,", resources)

  def test_icns_contains_all_seven_valid_png_sizes(self):
    data = ICON.read_bytes()
    self.assertEqual(data[:4], b"icns")
    declared = struct.unpack_from(">I", data, 4)[0]
    if declared != len(data):
      descriptions, pos = [], 8
      while pos + 8 <= len(data):
        part_size = struct.unpack_from(">I", data, pos + 4)[0]
        descriptions.append((data[pos:pos + 4], part_size, pos))
        if part_size < 8:
          break
        pos += part_size
      self.fail(f"ICNS header {declared}, bytes {len(data)}; entries {descriptions}")
    offset, seen = 8, set()
    while offset < len(data):
      kind = data[offset:offset + 4]
      count = struct.unpack_from(">I", data, offset + 4)[0]
      self.assertIn(kind, RESOLUTIONS)
      self.assertNotIn(kind, seen)
      self.assertGreater(count, 8)
      self.assertLessEqual(offset + count, len(data))
      check_png(data[offset + 8:offset + count], RESOLUTIONS[kind])
      seen.add(kind)
      offset += count
    self.assertEqual(offset, len(data))
    self.assertEqual(seen, set(RESOLUTIONS))


if __name__ == "__main__":
  unittest.main()
