# Security Policy

## Source maintenance and security support

PDF Magic Opener is maintained as **source code on `main`**, not through
numbered public application releases. There is **no public installable
production application or browser extension release**, no formal Semantic
Versioning scheme, no planned GitHub Releases distribution, and no
automatic application updater. Build tools may still require version
metadata; those internal values are not a release schedule or support promise.

The current `main` source is under active development. An exact Git commit
SHA identifies a particular checkout for troubleshooting, reproduction, and
security investigation. Older commits and locally built development
snapshots do **not** receive guaranteed maintenance, backports, or security
fixes. There is no newest-stable-version policy, supported-version matrix,
long-term-support window, or commitment to keep older builds working.

**Private vulnerability reports are welcome for any checkout**, including
older source snapshots. Maintainers may investigate and address defects in
the current source tree without promising a patch or response deadline for
a particular historical commit.

To update, review a [trusted source checkout](docs/application-update-delivery.md)
and follow the [upgrade and rollback guide](docs/upgrade-process.md).
Preserve user preferences, Finder actions, selected PDF associations,
quarantine, signature freshness, and the mandatory ClamAV **scan-before-open**
and file-integrity checks. If a safe update is unavailable, avoid opening
untrusted PDFs with an old development snapshot rather than weakening safety
protections.

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

Maintainers use [security fix prioritization](docs/security-fix-prioritization.md)
to assess urgency and schedule safe remediation. These internal priorities are
not response-time or public disclosure promises.

A security report does not authorize weakening or bypassing the installed
ClamAV scan gate, file-integrity checks, quarantine, or users' selected PDF
opening preferences. A clean scan is not a guarantee that a PDF is safe.

If a **published build or source archive may be compromised**, maintainers
should follow the [compromised release revocation runbook](docs/release-revocation.md)
to stop distribution, withdraw downloads, notify users, and verify recovery.
This does not relax private reporting or coordinated disclosure requirements.

For ordinary bugs or non-sensitive feature requests, use the
[public issue tracker](https://github.com/PDF-magic/opener/issues).
