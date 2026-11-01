#!/usr/bin/env python3
"""Check documentation layout without requiring third-party packages."""

from pathlib import Path
import re
import sys
from urllib.parse import unquote, urlsplit

ROOT = Path(__file__).resolve().parent.parent
DOCS = ROOT / "docs"
CATEGORIES = ("enhanced", "maximum", "pdf", "performance", "protection", "scanner")
KEBAB_MD = re.compile(r"[a-z0-9]+(?:-[a-z0-9]+)*\.md\Z")
MARKDOWN_LINK = re.compile(r"(?<!!)\[[^\]]*\]\(([^)]+)\)")


def check_docs():
  errors = []
  for category in CATEGORIES:
    folder = DOCS / category
    if not folder.is_dir():
      errors.append(f"Missing documentation folder: {folder.relative_to(ROOT)}")
      continue
    for page in folder.iterdir():
      if not page.is_file():
        errors.append(f"Unexpected nested entry: {page.relative_to(ROOT)}")
        continue
      if not KEBAB_MD.fullmatch(page.name) or page.stem.startswith(category + "-"):
        errors.append(f"Invalid or repetitive name: {page.relative_to(ROOT)}")
      for match in MARKDOWN_LINK.finditer(page.read_text(encoding="utf-8")):
        target = match.group(1).strip().split(" ", 1)[0]
        if not target or target.startswith(("#", "<")):
          continue
        url = urlsplit(target)
        if url.scheme or url.netloc:
          continue
        path = unquote(url.path)
        if path and not (page.parent / path).exists():
          errors.append(f"Broken link in {page.relative_to(ROOT)}: {target}")
  return errors


if __name__ == "__main__":
  errors = check_docs()
  for error in errors:
    print(error, file=sys.stderr)
  if errors:
    raise SystemExit(1)
  print("Documentation organization and local links verified.")
