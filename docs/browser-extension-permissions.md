# Browser extension permission requirements

PDF Magic Opener's **native macOS PDF handler works without a browser
extension**. No browser extension permissions are needed to install or use
the native scan-gated Finder PDF-opening workflow. Browser extensions in this
repository are currently **inactive scaffolds**: they cannot scan, sanitize,
intercept, or open PDFs, and their presence does not enable browser monitoring.

## Current declarations (not a list of permissions already granted)

The following is the reviewed Manifest V3 source/build contract. **Required**
means declared in the manifest's `permissions` or `host_permissions` field;
**optional** means the browser could ask later, after a user action and
separate feature activation. `None` means no declarations in that category.

| Build | Required API (`permissions`) | Required sites (`host_permissions`) | Optional API (`optional_permissions`) | Optional sites (`optional_host_permissions`) |
| --- | --- | --- | --- | --- |
| Shared / Chromium | None | None | `downloads` | None |
| Firefox | None | None | `downloads` | None |
| Safari | `nativeMessaging` | None | `downloads` | None |

- **Chromium-family / Firefox:** No browser API or website-origin permissions
  are required at installation. The shared and generated Firefox manifests
  declare only optional `downloads`, which is **not granted on install**.
- **Safari:** The Web Extension embedded in the macOS app declares
  **required `nativeMessaging`**, specifically for a containing-app messaging
  route. This is a Safari-only manifest difference, not a working scanner
  connection: its handler and background remain inactive. Installing the
  macOS app does **not** automatically enable the Safari extension; enabling
  an extension is controlled in Safari's extension settings.
- **All three:** No host origins are requested. No access to arbitrary
  websites, browsing history, cookies, tabs, `file://` URLs or all sites is
  required. The current manifests do not declare `optional_host_permissions`.

## Optional download monitoring and consent

The optional `downloads` browser permission could expose **download
filenames, source URLs and download history** to a future monitoring feature.
It is not required for native PDF opening, and the existing extension does
**not** start monitoring or display an active permission prompt. The
separately implemented request helper can ask only after monitoring is
explicitly enabled and a real, user-initiated gesture triggers the request.
Merely installing an extension, opening its popup, or declaring the
permission does not grant it. A denied, revoked, or unavailable permission
must leave monitoring disabled and must not silently restore access.

When a future reviewed feature is activated, the browser's own permission
dialog and extension/site permission controls govern whether the requested
access is allowed. You do not need to approve `downloads` to use the native
PDF handler. Never grant extra site or file access as a workaround for a
failed scan, unsupported PDF route, or inactive extension.

## Permissions that are not requirements

`notifications` and `storage` are **future-only** possibilities, not
currently requested permissions. `tabs`, `activeTab`, `scripting`,
`webRequest`, `history`, `cookies`, broad host origins (`<all_urls>`),
and direct local-file origin access are **not declared**. Future features
that genuinely need an exact website origin require a separate review and
explicit, appropriately scoped consent; no broad grant is preapproved.

Safari's macOS app-extension sandbox entitlement is distinct from browser
API permissions: its reviewed entitlement is the app sandbox only, with no
file, network or app-group exceptions. macOS Finder Automation prompts
encountered by some interactive tests are also **not** extension permissions.

**A browser permission never establishes that a PDF is safe.** The installed
native scanner independently enforces ClamAV signature freshness, file
integrity, quarantine handling, verified application handoff and the user's
chosen PDF destination. Denial or revocation cannot authorize bypassing any
of those gates.

## Technical contracts

- [Least-privilege API inventory](../extensions/webextension/permissions.md)
- [Host-origin scope](../extensions/webextension/host-permissions.md)
- [Permission explanations and data impact](../extensions/webextension/permission-explanations.md)
- [Opt-in download request contract](../extensions/webextension/src/download-permission.md)
- [Safari-specific packaging and permission tests](../extensions/safari/README.md)
