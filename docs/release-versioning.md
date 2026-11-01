# Release versioning scheme (opener-1135)

PDF Magic Opener uses **Semantic Versioning 2.0** for its **product release**
identity. A release has a three-part version `MAJOR.MINOR.PATCH`; an eligible
stable Git tag is **`vX.Y.Z`**, for example `v0.1.0` or `v1.2.3`.
The leading `v` belongs to the Git tag, **not** to package or application
version fields. Each number is a nonnegative decimal integer without leading
zeros (except `0`). Never reuse or move a published release tag.

## When to increment versions

- **MAJOR**: increment for a breaking change after `1.0.0`, such as
  incompatible configuration, public API, extension/native message contract,
  or documented scan-and-open behavior. Reset MINOR and PATCH to zero.
- **MINOR**: increment for backward-compatible features; reset PATCH to zero.
  While the project is at `0.x.y` (still pre-1.0 development), also increment
  MINOR for changes that break a development interface and disclose those
  changes in release notes. Do not claim pre-1.0 API stability.
- **PATCH**: increment for backward-compatible bug, security, or documentation
  fixes that warrant a release without introducing incompatible behavior.
  Describe security consequences and any upgrade requirements in the notes.

Use the **highest** increment required by the complete release, not one
version per commit or PR. A fix for a security issue is not automatically a
PATCH if it intentionally breaks compatibility. A release version does not
prove that a protection profile, browser interception route, or distribution
channel is active.

## Keep version identifiers aligned

Before creating a release tag, update these tracked declarations to exactly
the same `X.Y.Z` version:

| Component | Version source |
| --- | --- |
| Native macOS app and embedded Safari extension (Debug and Release) | `MARKETING_VERSION` entries in `PDFMagicOpener.xcodeproj/project.pbxproj`, which supply `CFBundleShortVersionString` |
| Chromium/Firefox WebExtension | `version` in `extensions/webextension/manifest.json` |
| WebExtension development/package metadata | `version` in `extensions/webextension/package.json` |

The macOS `CURRENT_PROJECT_VERSION` / `CFBundleVersion` is a separate
numeric **build** identifier. Advance it for each newly distributed macOS
build in accordance with Apple's channel requirements; it need not equal the
product's `X.Y.Z` and must not be silently reset when increasing MAJOR,
MINOR, or PATCH. Browser store versioning and separately approved updates
must meet each channel's requirements before publication.

The current checked-in product version is `0.1.0`; that declaration alone
does **not** certify any released binary. Do not modify version numbers
just to exercise a development build.

## Stable tags and publication

1. Finish the changes and version metadata bump in reviewed PRs. Record the
   user-visible changes, any breaking migration steps, and scanner-safety
   implications in the release notes. Preserve saved user preferences,
   quarantine, signature freshness, and scan-before-open gates.
2. Confirm the repository's
   [release gate](release-gate.md) and
   [browser distribution audit](browser-extension-distribution.md).
   Distribution is currently **NOT RELEASE READY**; the guarded release
   workflow must still fail closed. CI success does not authorize signing or
   distributing unsigned browser/macOS artifacts.
3. After distribution prerequisites are separately approved, create an
   immutable `vX.Y.Z` tag at the **exact current `main` commit**, and invoke
   the existing manual guarded workflow with that tag. It checks the exact
   commit, required CI, and matching product version metadata before it can
   publish a **source-only** GitHub Release. It does not create tags or ship
   signed applications or store packages.

Prerelease identifiers (such as `v1.0.0-rc.1`), build metadata
(`+build`), and other nonstable tags are **not accepted** by the current
stable source-release gate. A future prerelease distribution process requires
a separately reviewed workflow that explicitly labels prereleases and
satisfies the same scanner and distribution safeguards; do not use a stable
release to publish preview binaries.

ClamAV **engine versions** and antivirus **signature/database versions** are
independent of the PDF Magic Opener product version. Their supported-engine
and freshness policies remain enforced separately. See
[signature update process](scanner/signature-update-process.md) and
[upgrade process](upgrade-process.md).
