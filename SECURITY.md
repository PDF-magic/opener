# Security Policy

## Supported Versions

**Current status (2026-11-01): No public installable application release has
been published.** The checked-in native application and browser extension
identify themselves as `0.1.0`, but that is an **unreleased development
version**, not a supported production release. The support classifications
below apply to the **PDF Magic Opener application**, not to ClamAV's separate
engine or signature-database support policy.

| Application version / installation | Maintenance and security-fix support |
| --- | --- |
| Current `main` source (`0.1.0`, unreleased) | Active development and private security-report triage; **not a supported production build**. Changes and tests on `main` do not certify any public installation. |
| Older commits and locally built development snapshots (including earlier `0.1.0` builds) | **Unsupported**. No security-fix backports, maintenance guarantees, or compatibility support for those historical builds. |
| Published stable native macOS application versions | **None published; none currently supported.** |
| Production browser extension or Safari extension packages | **None published; none currently supported.** Development-only integrations are not covered by an application support promise. |

**Policy for future releases:** Once an installable stable native application
is publicly released and its distribution gate is explicitly cleared, **only
the newest published stable application version** will receive regular
maintenance and security fixes. Publishing a successor ends support for all
older stable application versions immediately; there is **no overlapping,
long-term-support, or backport window** by default. Prereleases, development
snapshots, and historical source commits are never supported production
versions. Any exception must be explicitly published in this table and the
release notes before it can be relied upon. A `vX.Y.Z` source tag or a
source-only GitHub Release does **not** alone establish an installable,
supported application release. No application release or automatic-updater
availability is implied by this forward-looking policy.

Users of older builds should review the [release notes](docs/release-notes.md)
and [versioning scheme](docs/release-versioning.md), then follow the
[trusted-source upgrade and rollback guide](docs/upgrade-process.md) when a
newer version is available. Do not bypass or weaken the ClamAV scan-before-open
gate, antivirus signature freshness, file-integrity checks, macOS quarantine,
or user-selected PDF opener to keep an older build running. Preserve custom
settings, scanner data, Finder actions, and PDF associations during migration.
If a verified safe upgrade is unavailable, avoid using the old build to open
untrusted PDFs rather than disabling protections.

**Private vulnerability reports are welcome for any version**, including
unsupported builds. Reporting does not mean that an older version will be
patched or that a remediation deadline is guaranteed; maintainers can assess
impact and address issues on the current development tree or latest supported
release as applicable. Follow the confidential reporting instructions below.

## Report a security vulnerability

Please report suspected vulnerabilities in PDF Magic Opener **privately**. This includes
the macOS scan-before-open gate, ClamAV integration, quarantine and file-integrity
checks, browser extensions, native messaging, PDF parsing, and dependencies.
**Do not publish exploit details, a proof of concept, malicious PDFs, or sensitive
diagnostics in a public GitHub issue, pull request, discussion, or CI log.**

1. Visit the [repository's private vulnerability reporting page](https://github.com/PDF-magic/opener/security/advisories/new).
   If GitHub displays **Report a vulnerability**, submit the report there.
   This option depends on the repository maintainers enabling private vulnerability reporting;
   its availability is **not guaranteed**.
2. If private reporting is unavailable, seek a private contact method published by
   the repository maintainers. If none is available, open a
   [public issue](https://github.com/PDF-magic/opener/issues/new) **only to request
   a private reporting channel**. Do not include vulnerability details, affected
   secrets, attack instructions, or attachments in that public request.
3. Once you have a private channel, provide the details below there. Keep further
   discussion and any reproduction material private until disclosure is coordinated.

## What to include in a private report

- A concise description of the suspected vulnerability, its security impact, and
  any conditions needed to reproduce it.
- The affected application or extension version (or commit), macOS and browser
  versions where relevant, and the affected component.
- Steps to reproduce, expected versus observed behavior, and a minimal,
  non-destructive proof of concept **only when safe to share privately**.
- Any mitigation you have tested, and a way for maintainers to ask follow-up questions.

Remove personal information, paths, tokens, credentials, and confidential document
contents from logs and screenshots. Do not send anyone's private PDF documents or
attempt exploitation against other users or systems. Do not upload malware samples
to public repositories or CI fixtures.

## What happens next

Maintainers can assess a confidential report, ask for clarification, investigate
the impact, and coordinate a fix and any public advisory with the reporter.
**No acknowledgement or remediation deadline is promised by this document.**
Please avoid public disclosure of actionable details while a report is being
investigated and coordinate any publication with the maintainers.

A security report does not authorize weakening or bypassing the installed
ClamAV scan gate, file-integrity checks, quarantine, or users' selected PDF
opening preferences. A clean scan is not a guarantee that a PDF is safe.

For ordinary bugs or non-sensitive feature requests, use the
[public issue tracker](https://github.com/PDF-magic/opener/issues).
