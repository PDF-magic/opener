# Build metadata (no product release versioning)

PDF Magic Opener does **not** use a public Semantic Versioning policy,
numbered release schedule, Git release tags, or a supported-version matrix.
The source checkout is identified by its **Git commit SHA**. Changes to
`main` and its commit history are the source of truth, and a commit is
not an installable public release.

## Required build metadata

Certain tools require a syntactically valid version field even when
no formal product versioning is used:

| Component | Technical field |
| --- | --- |
| Native macOS application and bundled Safari extension | `MARKETING_VERSION` and `CURRENT_PROJECT_VERSION` in `PDFMagicOpener.xcodeproj/project.pbxproj`, consumed by `CFBundleShortVersionString` / `CFBundleVersion` |
| Chromium/Firefox WebExtension | `version` in `extensions/webextension/manifest.json` |
| WebExtension build/package tooling | `version` in `extensions/webextension/package.json` |

These are **required technical identifiers**, not announcements or promises
of support. The checked-in `0.1.0` is a development placeholder; it does
not mean a downloadable production build has been released. Preserve
well-formed metadata and keep fields compatible with build and package
requirements. Do not remove them, fabricate a supported release, or advance
them solely to imply public product progress.

There is no requirement to classify commits as MAJOR, MINOR, or PATCH, and
no need to create `vX.Y.Z` tags for ordinary source changes. Any legacy
source-only release gate is separate from the source-checkout installation
process and **is not a planned distribution channel**. It is **NOT RELEASE READY**
and must remain fail-closed rather than publish unapproved binaries. No
stable or prerelease tags are needed for routine source updates.

## Safe source updates

Review the exact Git commit, changed behavior, possible migration needs,
and scanner safety before updating from a complete trusted source
checkout. Preserve user settings, default PDF-handler choices, Finder
customizations, quarantine, signature freshness, file-integrity checks,
and the native scan-before-open gate. See the
[manual update policy](application-update-delivery.md) and
[upgrade instructions](upgrade-process.md).

ClamAV engine and signature-database versions still follow their own
compatibility and freshness requirements; discontinuing **product release
versioning** does not weaken those scanner checks. See
[signature updates](scanner/signature-update-process.md).
