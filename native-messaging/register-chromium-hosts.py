#!/usr/bin/env python3
"""Opt-in, per-user macOS native host registration for supported Chromium browsers.

Reuses the separately approved Chrome registration from opener-0639. Never creates
extension origins, grants browser permissions, or touches PDF scanner state.
"""

import argparse
import json
import os
from pathlib import Path
import re
import stat
import sys
import tempfile

HOST_NAME = "org.pdfmagic.opener"
MANIFEST_FILENAME = HOST_NAME + ".json"
# Only independently supported Chromium-family browsers from browser_registry.py.
# Opera documents using Chrome's native host directory on macOS.
BROWSER_LOCATIONS = {
    "chrome": "Google/Chrome",
    "chromium": "Chromium",
    "brave": "BraveSoftware/Brave-Browser",
    "edge": "Microsoft Edge",
    "vivaldi": "Vivaldi",
    "opera": "Google/Chrome",
    "arc": "Arc/User Data",
}
ORIGIN_PATTERN = re.compile(r"chrome-extension://[a-p]{32}/\Z")


class RegistrationError(ValueError):
    """An unsafe, incomplete, or conflicting native host registration."""


def validated_manifest(source):
    source = Path(source)
    if not source.is_absolute() or source.is_symlink() or not source.is_file():
        raise RegistrationError("manifest must be an absolute regular file, not a link")
    if source.stat().st_size > 65536:
        raise RegistrationError("manifest exceeds size limit")
    contents = source.read_bytes()
    try:
        manifest = json.loads(contents)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise RegistrationError("invalid native host JSON manifest") from exc
    if not isinstance(manifest, dict) or manifest.get("name") != HOST_NAME:
        raise RegistrationError("unexpected native host identifier")
    if manifest.get("type") != "stdio" or not isinstance(manifest.get("description"), str) or not manifest["description"].strip():
        raise RegistrationError("invalid native host transport or description")
    host_path = manifest.get("path")
    if not isinstance(host_path, str) or not Path(host_path).is_absolute():
        raise RegistrationError("native host executable path must be absolute")
    host = Path(host_path)
    if host.is_symlink() or not host.is_file() or not os.access(host, os.X_OK):
        raise RegistrationError("native host must be an executable regular file")
    origins = manifest.get("allowed_origins")
    if (not isinstance(origins, list) or not origins or
            any(not isinstance(o, str) or not ORIGIN_PATTERN.fullmatch(o) for o in origins) or
            len(origins) != len(set(origins))):
        raise RegistrationError("a nonempty, unique, exact Chromium extension origin allowlist is required")
    return contents


def _check_directory_chain(home, directory):
    if not home.is_absolute() or home.is_symlink() or not home.is_dir():
        raise RegistrationError("home must be a real, absolute directory")
    relative = directory.relative_to(home)
    path = home
    for part in relative.parts:
        path = path / part
        if path.is_symlink() or (path.exists() and not path.is_dir()):
            raise RegistrationError("registration directory is not a real directory: " + str(path))


def register_chromium_hosts(home=None):
    """Extend the existing Chrome registration to other supported macOS browsers.

    Preflight *all* destinations first; do not replace user-customized manifests.
    Same-content registrations are left untouched. No system-wide writes.
    """
    home = Path(home) if home is not None else Path.home()
    chrome_source = home / "Library" / "Application Support" / BROWSER_LOCATIONS["chrome"] / "NativeMessagingHosts" / MANIFEST_FILENAME
    _check_directory_chain(home, chrome_source.parent)
    contents = validated_manifest(chrome_source)
    locations = {
        browser: home / "Library" / "Application Support" / relative / "NativeMessagingHosts" / MANIFEST_FILENAME
        for browser, relative in BROWSER_LOCATIONS.items()
    }
    # Chrome and Opera are already covered by the prerequisite Chrome registration.
    targets = sorted(set(locations.values()) - {chrome_source})
    for target in targets:
        _check_directory_chain(home, target.parent)
        if target.is_symlink() or (target.exists() and not target.is_file()):
            raise RegistrationError("registration path is not a regular file: " + str(target))
        if target.exists() and target.read_bytes() != contents:
            raise RegistrationError("existing native host registration differs: " + str(target))

    for target in targets:
        if target.exists():
            continue
        target.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        _check_directory_chain(home, target.parent)
        file_descriptor, temporary = tempfile.mkstemp(prefix=".pdfmagic-host-", dir=target.parent)
        try:
            with os.fdopen(file_descriptor, "wb") as output:
                output.write(contents)
                output.flush()
                os.fsync(output.fileno())
            os.chmod(temporary, stat.S_IRUSR | stat.S_IWUSR)
            # Hard-link creation is atomic and never replaces a concurrent file.
            try:
                os.link(temporary, target, follow_symlinks=False)
            except FileExistsError as exc:
                raise RegistrationError("registration changed during installation: " + str(target)) from exc
        finally:
            if os.path.exists(temporary):
                os.unlink(temporary)
    return locations


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    args = parser.parse_args(argv)
    if sys.platform != "darwin":
        parser.error("actual registration is supported on macOS only")
    try:
        paths = register_chromium_hosts()
    except (OSError, RegistrationError) as exc:
        parser.error(str(exc))
    for browser, path in paths.items():
        print(f"{browser}: {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
