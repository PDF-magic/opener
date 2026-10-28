# Unsupported PDF features — response policy (opener-0254)

The installed scanner remains the only active protection gate. The definitions
in `unsupported_pdf_features.py` specify what **must happen if a trusted PDF
inspection step cannot fully inspect a feature**. They do not inspect a PDF,
recognize features, select a profile, or claim that additional validators exist.

- **Deny opening:** no destination application or optional fallback is launched.
- **Retain quarantine:** an unverified file remains quarantined; no bypass or
  manual approval is granted by the policy.
- **No clean result:** do not publish or cache a clean verdict. An unsupported
  filter, active or embedded content, incomplete inspection, or unknown finding
  maps to `incompleteScan`. Encryption that prevents inspection maps to
  `encrypted`. Neither status authorizes opening.
- **Explain safely:** show a fixed, path-free explanation that inspection could
  not be completed. Do not report an unsupported feature as a malware detection,
  echo document content, or invent a successful safety check.

**Current enforcement:** ClamAV already fails closed for encrypted/oversized
heuristics, nonzero scan exits, warnings, and scans lacking a complete clean
result. The regression tests exercise those gates. This policy contract is
not a new PDF parser; extending detection to further unsupported PDF features
requires a separate verified inspector integrated **before** a clean result can
be cached or any file is unquarantined and handed off. Standard, Enhanced and
Maximum remain unselectable until their separate planned controls are built.
