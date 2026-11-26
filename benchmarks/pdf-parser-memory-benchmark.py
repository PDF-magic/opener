#!/usr/bin/env python3
"""Offline, synthetic PDF-structure peak-RSS comparison; never scan user files."""
import argparse
from importlib.metadata import PackageNotFoundError, version
from io import BytesIO
import json
import resource
import subprocess
import sys

PARSERS = ("pypdf", "pikepdf", "pymupdf")
MAX_PAGES = 1024
MAX_STREAM_BYTES = 8 * 1024 * 1024


def synthetic_pdf(pages, stream_bytes):
  if type(pages) is not int or not 1 <= pages <= MAX_PAGES:
    raise ValueError("Page count exceeds benchmark bounds")
  if type(stream_bytes) is not int or not 0 <= stream_bytes <= MAX_STREAM_BYTES:
    raise ValueError("Stream size exceeds benchmark bounds")
  data = bytearray(b"%PDF-1.7\n%\xe2\xe3\xcf\xd3\n")
  offsets = [0]

  def add_object(index, contents):
    offsets.append(len(data))
    data.extend(f"{index} 0 obj\n".encode("ascii"))
    data.extend(contents)
    data.extend(b"\nendobj\n")

  add_object(1, b"<< /Type /Catalog /Pages 2 0 R >>")
  kids = b" ".join(f"{i} 0 R".encode("ascii") for i in range(3, pages + 3))
  add_object(2, b"<< /Type /Pages /Count " + str(pages).encode("ascii") +
             b" /Kids [" + kids + b"] >>")
  for index in range(3, pages + 3):
    add_object(index, b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] " +
               b"/Contents " + str(pages + 3).encode("ascii") + b" 0 R >>")
  payload = b" " * stream_bytes
  add_object(pages + 3, b"<< /Length " + str(len(payload)).encode("ascii") +
             b" >>\nstream\n" + payload + b"\nendstream")
  startxref = len(data)
  data.extend(f"xref\n0 {len(offsets)}\n0000000000 65535 f \n".encode("ascii"))
  for offset in offsets[1:]:
    data.extend(f"{offset:010d} 00000 n \n".encode("ascii"))
  data.extend(b"trailer\n<< /Size " + str(len(offsets)).encode("ascii") +
              b" /Root 1 0 R >>\n")
  data.extend(f"startxref\n{startxref}\n%%EOF\n".encode("ascii"))
  return bytes(data)


def parse_structure(parser, data):
  if parser == "pypdf":
    from pypdf import PdfReader
    return len(PdfReader(BytesIO(data), strict=True).pages)
  if parser == "pikepdf":
    import pikepdf
    with pikepdf.Pdf.open(BytesIO(data)) as document:
      return len(document.pages)
  if parser == "pymupdf":
    import pymupdf
    with pymupdf.open(stream=data, filetype="pdf") as document:
      return document.page_count
  raise ValueError("Unknown parser")


def package_version(parser):
  return version("PyMuPDF" if parser == "pymupdf" else parser)


def sample(parser, pages, stream_bytes):
  if parser not in PARSERS:
    raise ValueError("Unsupported parser")
  pdf = synthetic_pdf(pages, stream_bytes)
  if parse_structure(parser, pdf) != pages:
    raise ValueError("Parser returned a different page count")
  rss = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
  mib = rss / (1024 * 1024 if sys.platform == "darwin" else 1024)
  return {"parser": parser, "version": package_version(parser),
          "pages": pages, "input_bytes": len(pdf),
          "peak_rss_mib": round(mib, 2)}


def main():
  cli = argparse.ArgumentParser(description=__doc__)
  cli.add_argument("--parser", choices=(*PARSERS, "all"), default="all")
  cli.add_argument("--pages", type=int, default=512)
  cli.add_argument("--stream-bytes", type=int, default=4 * 1024 * 1024)
  cli.add_argument("--worker", action="store_true", help=argparse.SUPPRESS)
  args = cli.parse_args()
  synthetic_pdf(args.pages, args.stream_bytes)
  if args.worker:
    if args.parser == "all":
      cli.error("Worker requires exactly one parser")
    print(json.dumps(sample(args.parser, args.pages, args.stream_bytes)))
    return
  results = []
  for parser in PARSERS if args.parser == "all" else (args.parser,):
    try:
      package_version(parser)
    except PackageNotFoundError:
      results.append({"parser": parser, "status": "not-installed"})
      continue
    process = subprocess.run(
      [sys.executable, __file__, "--worker", "--parser", parser,
       "--pages", str(args.pages), "--stream-bytes", str(args.stream_bytes)],
      capture_output=True, text=True, check=False, timeout=60,
    )
    if process.returncode:
      results.append({"parser": parser, "status": "failed"})
    else:
      results.append({"status": "ok", **json.loads(process.stdout)})
  print(json.dumps(results, sort_keys=True, indent=2))


if __name__ == "__main__":
  main()
