# Application update delivery policy (opener-1158)

PDF Magic Opener uses a **user-initiated, whole-application update** for its
native macOS app and installed scan-gated PDF handler. **There is no background
application updater, automatic download, in-app install action, or production
application-update feed.** The Updates settings pane displays installed app
version information; its manual buttons concern **ClamAV definitions**, not a
new application version. Do not confuse the two update streams.

## Current delivery: trusted source and explicit reinstallation

Until a signed release channel has passed its separate distribution gates,
new application code is available only through a **complete trusted checkout**
of the official [PDF-magic/opener repository](https://github.com/PDF-magic/opener).
Select and review the specific desired commit/version; do not treat a CI
artifact, an unsigned archive, a random mirror, or a copied installer script
as an installable public update. There is no published binary update channel.

Delivery and installation are distinct: acquiring a newer trusted checkout
does not change a user's installed application. On macOS 13 or later, after
reviewing changes and prerequisites, finish any active scans and run the
existing installer **as the normal user**, from the root of that checkout:

```sh
bash install-allow-and-open.sh
```

The user chooses when to run this action; nothing polls, downloads, launches,
or silently installs an application update. Follow the
[upgrade procedure](upgrade-process.md) for checks before the upgrade,
post-install verification, migration status, and failed-upgrade rollback.
Running the installer must not reset selected PDF destinations, hijack the
current macOS default PDF application, overwrite unrelated Finder actions,
replace a compatible ClamAV installation, or discard signatures or other
saved preferences. The existing explicit-consent and rollback controls apply.

The installed PDF handler remains responsible for mandatory current
ClamAV signatures, complete clean scanning, file-integrity verification,
quarantine preservation, and verified destination handoff. Updating the app
does **not** by itself establish scanner health or authorize a PDF to open.

## Future public delivery decision (not implemented)

The intended public **native macOS application** delivery channel is a
**versioned, signed and notarized application archive** linked from
**official GitHub Releases**, downloaded and installed only after a user chooses to
update. A release must have a reviewed stable `vX.Y.Z` identifier, release notes,
checksums, independently verified Developer ID signatures and Apple
notarization, and installation/upgrade verification before it can be offered
as a trusted binary. An independently approved release workflow and download
verification procedure are prerequisites; this document does **not** publish
an artifact, configure signing, implement a feed, or authorize an auto-updater.

The existing [guarded GitHub release](release-gate.md) is **source-only**,
and the [distribution audit](browser-extension-distribution.md) currently
reports **NOT RELEASE READY**. Its gate refuses publication until
prerequisites are resolved. Successful CI, an unsigned ZIP, a GitHub source
archive, or a tag alone is not a signed/notarized app update. The
[versioning policy](release-versioning.md) sets product version identity, not
installation authorization. Future changes to the delivery mechanism
(including a background updater or new publisher) require separate approval,
a threat review, consent design, and regression testing.

## Different update channels

- **ClamAV signature definitions** use the existing FreshClam update
  agent/manual actions and retain the 48-hour freshness gate; they are
  independent of application version delivery. ClamAV engine management is
  likewise separate. See [signature updates](scanner/signature-update-process.md).
- **Browser extensions** have their own Chrome/Edge/Opera/Firefox/Safari
  store/signing and browser-managed update requirements. Current unsigned
  development packages are inactive and not installable public updates.
  See [browser distribution](browser-extension-distribution.md) and
  [developer installation](browser-extension-installation.md).
- An application update must not silently opt users into browser extension
  installation, change extension permissions, or rewrite native messaging
  allowlists. Existing user customizations remain authoritative.

**Failure behavior:** A missing, untrusted, unsigned, or unavailable release
is **not** an instruction to bypass Gatekeeper or use an unsigned CI artifact.
Keep the existing installation and its protections; if an explicit
reinstallation fails, follow the documented migration/rollback process and
reverify the scanner before opening PDFs.
