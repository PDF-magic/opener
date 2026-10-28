#!/usr/bin/env python3
"""Read-only identification of stable and preview macOS browser app bundles.

This reports release identity, not PDF-launch approval, installation trust,
or a list of supported browsers. The scanner and target-app preferences do
not consult this module.
"""

from dataclasses import asdict, dataclass
import json
import os
from pathlib import Path
import plistlib
import stat
import sys


# Exact macOS CFBundleIdentifiers: do not use prefixes or executable names.
# The stable and preview IDs are kept separate so simultaneous installations
# cannot silently collapse into one browser choice.
_RELEASES = {
    "com.brave.Browser": ("Brave", "stable"),
    "com.brave.Browser.beta": ("Brave", "beta"),
    "com.brave.Browser.nightly": ("Brave", "nightly"),
    "com.google.Chrome": ("Google Chrome", "stable"),
    "com.google.Chrome.beta": ("Google Chrome", "beta"),
    "com.google.Chrome.dev": ("Google Chrome", "dev"),
    "com.google.Chrome.canary": ("Google Chrome", "canary"),
    "org.mozilla.firefox": ("Mozilla Firefox", "stable"),
    "org.mozilla.firefoxdeveloperedition": ("Mozilla Firefox", "developer"),
    "org.mozilla.nightly": ("Mozilla Firefox", "nightly"),
    "com.microsoft.edgemac": ("Microsoft Edge", "stable"),
    "com.microsoft.edgemac.Beta": ("Microsoft Edge", "beta"),
    "com.microsoft.edgemac.Dev": ("Microsoft Edge", "dev"),
    "com.microsoft.edgemac.Canary": ("Microsoft Edge", "canary"),
    "com.apple.Safari": ("Safari", "stable"),
    "com.apple.SafariTechnologyPreview": ("Safari", "technology-preview"),
    "org.chromium.Chromium": ("Chromium", "stable"),
    "com.vivaldi.Vivaldi": ("Vivaldi", "stable"),
    "com.vivaldi.Vivaldi.snapshot": ("Vivaldi", "snapshot"),
    "com.operasoftware.Opera": ("Opera", "stable"),
    "company.thebrowser.Browser": ("Arc", "stable"),
}


@dataclass(frozen=True)
class BrowserRelease:
    bundle_id: str
    family: str | None
    channel: str
    kind: str
    version: str | None


def identify_release(info):
    """Classify only explicitly recognized identities; never infer from names.

    Some non-side-by-side Chrome Beta/Dev installations share the stable
    CFBundleIdentifier. The Keystone channel in Info.plist is authoritative
    for those builds; without it, their release channel is unknown.
    """
    bundle_id = info.get("CFBundleIdentifier")
    if not isinstance(bundle_id, str):
        bundle_id = ""
    version = info.get("CFBundleShortVersionString")
    if not (isinstance(version, str) and 0 < len(version) <= 64
            and all(character.isprintable() for character in version)):
        version = None
    release = _RELEASES.get(bundle_id)
    if release is None:
        return BrowserRelease(bundle_id, None, "unknown", "unknown", version)
    family, channel = release

    if bundle_id == "com.google.Chrome":
        # The exact Chrome bundle ID does NOT always imply a stable release.
        # Chromium's own channel identification reads KSChannelID only for
        # Keystone-enabled Google Chrome installations.
        if not isinstance(info.get("KSProductID"), str) or not info["KSProductID"]:
            channel = "unknown"
        else:
            channel_id = info.get("KSChannelID")
            if channel_id is None or channel_id == "":
                channel = "stable"
            elif channel_id in ("beta", "dev", "canary"):
                channel = channel_id
            else:
                channel = "unknown"

    kind = "unknown" if channel == "unknown" else (
        "stable" if channel == "stable" else "preview"
    )
    return BrowserRelease(bundle_id, family, channel, kind, version)


def inspect_app_bundle(application):
    """Read the named application's Info.plist without launching it.

    This is metadata classification only. The existing signed/native PDF
    preflight must still independently verify any selected launch target.
    """
    app = Path(application)
    info_path = app / "Contents" / "Info.plist"
    if (app.suffix.lower() != ".app" or app.is_symlink()
            or not app.is_dir() or (app / "Contents").is_symlink()):
        raise ValueError("Not a readable application bundle")
    try:
        descriptor = os.open(info_path, os.O_RDONLY | os.O_NOFOLLOW)
        with os.fdopen(descriptor, "rb") as stream:
            length = os.fstat(stream.fileno())
            if not stat.S_ISREG(length.st_mode) or length.st_size > 1024 * 1024:
                raise ValueError("Invalid application metadata")
            data = stream.read(1024 * 1024 + 1)
        if len(data) > 1024 * 1024:
            raise ValueError("Invalid application metadata")
        info = plistlib.loads(data)
    except (OSError, plistlib.InvalidFileException, TypeError, ValueError) as error:
        raise ValueError("Cannot read application metadata") from error
    if not isinstance(info, dict):
        raise ValueError("Invalid application metadata")
    return identify_release(info)


def main(arguments):
    if len(arguments) != 1:
        print("Usage: browser_release.py /path/to/Browser.app", file=sys.stderr)
        return 2
    try:
        release = inspect_app_bundle(arguments[0])
    except ValueError:
        print("Cannot identify the browser application.", file=sys.stderr)
        return 1
    print(json.dumps(asdict(release), sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
