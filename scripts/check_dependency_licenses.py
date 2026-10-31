#!/usr/bin/env python3
"""Offline license-review gate for declared installation/test dependencies.

Checks reviewed versions and license evidence, never executes dependencies,
installs packages, reads user configuration, or changes scanner behavior.
"""

import json
from pathlib import Path
import re
import shlex
import sys

ROOT = Path(__file__).resolve().parents[1]
INVENTORY = "docs/dependency-licenses.json"
REQUIREMENTS = "requirements-enhanced-pdf.txt"
BROWSER_PACKAGE = "extensions/webextension/package.json"

# Changing a pin or licensing choice requires explicit review here AND in the
# evidence-backed inventory. It must not silently pass by updating JSON alone.
REVIEWED = {
  "clamav": ((), "GPL-2.0-only"),
  "pypdf": (("5.9.0", "6.21.3"), "BSD-3-Clause"),
  "pillow": (("11.3.0",), "MIT-CMU"),
  "cryptography": (("46.0.4",), "Apache-2.0 OR BSD-3-Clause"),
  "pymupdf": (("2.0",), "AGPL-3.0-only OR LicenseRef-Artifex-Commercial"),
}
PIN = re.compile(r"([a-zA-Z][a-zA-Z0-9_.-]*)==([0-9][a-zA-Z0-9.]*)\Z")


class LicenseReviewError(ValueError):
  """An unreviewed installation input must not pass the license check."""


def _inventory(root):
  data = json.loads((root / INVENTORY).read_text(encoding="utf-8"))
  if not isinstance(data, dict) or set(data) != set(REVIEWED):
    raise LicenseReviewError("Unreviewed or missing dependency license entry")
  for key, (versions, expression) in REVIEWED.items():
    item = data[key]
    if not isinstance(item, dict) or set(item) != {
      "versions", "license", "source", "distribution_requirements", "use"
    }:
      raise LicenseReviewError("Invalid license record for " + key)
    if (item["versions"] != list(versions) or item["license"] != expression
        or not isinstance(item["source"], str)
        or not item["source"].startswith("https://")
        or not isinstance(item["distribution_requirements"], str)
        or len(item["distribution_requirements"].strip()) < 30
        or not isinstance(item["use"], str)
        or len(item["use"].strip()) < 12):
      raise LicenseReviewError("Missing or changed license review for " + key)
  return data


def _requirement(line, found):
  match = PIN.fullmatch(line)
  if match is None:
    raise LicenseReviewError("Dependency must use an explicitly reviewed version: " + line)
  name, version = match.groups()
  name = name.lower().replace("_", "-")
  if name not in REVIEWED or version not in REVIEWED[name][0]:
    raise LicenseReviewError("Unreviewed dependency or version: " + name + "==" + version)
  found.add((name, version))


def _requirement_file(root, relative, found):
  if relative != REQUIREMENTS:
    raise LicenseReviewError("Unreviewed pip requirements file: " + relative)
  for line in (root / relative).read_text(encoding="utf-8").splitlines():
    value = line.strip()
    if value and not value.startswith("#"):
      _requirement(value, found)


def _workflow_install(line, root, found):
  # No shell execution: inspect only literal, one-line pip installation
  # commands found in GitHub workflows. Unsupported arguments fail closed.
  tokens = shlex.split(line.split("pip install", 1)[1].strip(), comments=True)
  i = 0
  while i < len(tokens):
    token = tokens[i]
    if token in ("--disable-pip-version-check", "--no-deps", "--no-cache-dir"):
      i += 1
    elif token in ("-r", "--requirement"):
      if i + 1 >= len(tokens):
        raise LicenseReviewError("Missing requirements filename")
      _requirement_file(root, tokens[i + 1], found)
      i += 2
    elif token.startswith("-") or token in ("&&", ";", "|"):
      raise LicenseReviewError("Unreviewed pip installation argument: " + token)
    else:
      _requirement(token, found)
      i += 1


def check(root=ROOT):
  root = Path(root)
  _inventory(root)
  found = set()
  _requirement_file(root, REQUIREMENTS, found)
  workflows = sorted((root / ".github/workflows").glob("*.yml"))
  if not workflows:
    raise LicenseReviewError("No CI workflow files to review")
  for path in workflows:
    for line in path.read_text(encoding="utf-8").splitlines():
      if "pip install" in line and not line.lstrip().startswith("#"):
        _workflow_install(line, root, found)
  for name, (versions, _) in REVIEWED.items():
    if name != "clamav":
      for version in versions:
        if (name, version) not in found:
          raise LicenseReviewError("Reviewed dependency pin no longer declared: "
                                   + name + "==" + version)
  package = json.loads((root / BROWSER_PACKAGE).read_text(encoding="utf-8"))
  for field in ("dependencies", "devDependencies", "optionalDependencies", "peerDependencies"):
    if package.get(field):
      raise LicenseReviewError("Unreviewed WebExtension dependency: " + field)
  installer = (root / "install-allow-and-open.sh").read_text(encoding="utf-8")
  # The reviewed package route requires a validated Homebrew executable and
  # a separate explicit controlling-terminal approval before installation.
  approved_brew_route = (
    'brew_executable="$(python3 "$script_dir/scripts/detect_homebrew.py")"' in installer
    and 'python3 "$script_dir/scripts/confirm_clamav_install.py"' in installer
    and 'HOMEBREW_NO_AUTO_UPDATE=1 "$brew_executable" install clamav' in installer
    and "if ! [ -x /opt/homebrew/bin/clamscan ]" in installer
  )
  if not approved_brew_route or "clamscan" not in installer:
    raise LicenseReviewError("ClamAV installation route changed; recheck GPL terms")
  project_license = (root / "LICENSE").read_text(encoding="utf-8")
  if "GNU AFFERO GENERAL PUBLIC LICENSE" not in project_license:
    raise LicenseReviewError("Application license changed; review dependency compatibility")
  return found


if __name__ == "__main__":
  try:
    found = check()
  except (OSError, ValueError) as error:
    print("Dependency license review FAILED: " + str(error), file=sys.stderr)
    sys.exit(1)
  print("Reviewed dependency licensing: ClamAV GPLv2 and "
        + ", ".join(sorted(name + "==" + version for name, version in found)))
