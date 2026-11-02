# Release notes

**Publication state: UNRELEASED.** These development notes are published as
repository documentation for transparency. They are **not** a GitHub Release,
a signed application, an approved browser extension, or installation advice.
The [distribution audit](browser-extension-distribution.md) remains
**NOT RELEASE READY**; publishing this page does not clear that gate.

## Development snapshot — 0.1.0 (unreleased)

The following describes capabilities and limitations of the checked-in
development source. It does **not** assert that a distributable version 0.1.0
has been published or independently validated on every supported macOS version.

### Local PDF opening and security

- The native macOS PDF handler runs a local **ClamAV** check before handing
  a file to the chosen PDF-capable application, with antivirus signature
  freshness and file-integrity checks. Untrusted or incomplete results
  **fail-closed** rather than authorizing an open.
- The default post-scan destination is Brave, but users can explicitly
  choose a supported installed browser or a verified custom application.
  Existing saved choices are preserved rather than silently reset.
- Quarantine, the installed scan gate, and users' PDF associations are not
  bypassed by the presence of browser integration source or settings previews.

### App and extension development

- The source includes a macOS SwiftUI settings application and a native
  PDF scan-gated opening route for locally available files.
- Standard, Enhanced, and Maximum are **preview-only** protection
  definitions; the currently enforced Built-in scan gate remains distinct.
- Browser extension packages and Safari integration are development
  candidates, **not active, store-approved scan-before-render protection**.
  Inline browser viewers and remote PDFs are not universally intercepted.

### Release availability and limitations

- Supported minimum target: macOS 13 Ventura; current CI does not
  independently certify every eligible macOS release.
- No signed/notarized macOS app, store-signed browser extension, or public
  installable release is announced by these notes. Follow the
  [distribution audit](browser-extension-distribution.md) for remaining
  signing, publisher, review, and installation prerequisites.
- Development builds are not a substitute for the verified native scanning
  and safe opening installation path. Preserve local preferences and
  security checks when following the [upgrade guide](upgrade-process.md).

## How actual GitHub Release notes will be published

After separate approval of the distribution prerequisites, maintainers must
follow the [release versioning](release-versioning.md) and
[fail-closed release gate](release-gate.md) procedures. The existing,
manually dispatched **Guarded GitHub release** workflow verifies an existing
stable tag on the exact current `main` commit, matching component versions,
distribution readiness, and required CI checks. Only then does it create a
**source-only** GitHub Release with generated release notes. It never
publishes unsigned browser packages or macOS application artifacts.

Review the generated release notes and any migration or security advisories
before announcing a release. This document is a public development snapshot,
not an authorization to bypass the gate or declare a release complete.
