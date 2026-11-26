"""Known macOS bundle identifiers for PDF-capable browser applications.

This catalog is for discovery and UI labels, not an installation check or a
security allowlist. The existing macOS verifier must validate each selected
application, and user-configured bundle identifiers remain supported.
"""

from types import MappingProxyType

SUPPORTED_BROWSERS = MappingProxyType({
    "brave": "com.brave.Browser",
    "chrome": "com.google.Chrome",
    "chromium": "org.chromium.Chromium",
    "edge": "com.microsoft.edgemac",
    "vivaldi": "com.vivaldi.Vivaldi",
    "opera": "com.operasoftware.Opera",
    "arc": "company.thebrowser.Browser",
    "firefox": "org.mozilla.firefox",
    "safari": "com.apple.Safari",
})

SUPPORTED_BROWSER_BUNDLE_IDS = frozenset(SUPPORTED_BROWSERS.values())
DEFAULT_BROWSER_BUNDLE_ID = SUPPORTED_BROWSERS["brave"]
