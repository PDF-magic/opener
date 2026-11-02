# Compromised release withdrawal and revocation (opener-1170)

**Current status: NOT RELEASE READY.** No public installable macOS application or store-signed browser extension has been approved, and the guarded GitHub release workflow is **source-only**. This is an incident-response runbook, **not authorization** to publish, sign, notarize, activate or automatically update anything. See the [release gate](release-gate.md), [distribution audit](browser-extension-distribution.md), and [private security reporting](../SECURITY.md).

## Declare an incident and preserve evidence

The maintainer acting as **incident lead** coordinates security response; the repository administrator controls publishing permissions and the release owner verifies withdrawal. Treat a release as suspect when its source, checksum, signing or publishing identity, build provenance, scanner gate, or shipped artifact may have been compromised. **Do not wait for exploit proof** before halting distribution of a plausibly affected build.

1. Open a **private** incident through the [security reporting process](../SECURITY.md). Record every approval, responsible person and UTC time. Keep exploit details, access tokens, credentials, sensitive diagnostics and customer PDFs out of public issues and CI logs.
2. Privately inventory affected vX.Y.Z tags, commit SHA, release URL, published asset filenames and SHA-256, channels, extension IDs or native build IDs (when applicable), affected versions, and known download/installation exposure. Compare **published bytes** and provenance with the reviewed build; neither a tag name nor passing CI alone proves safety.
3. **Preserve immutable evidence** and suspicious bytes in restricted incident storage before removing public downloads; record their hashes. Keep private findings private; publish only non-sensitive version identities, hashes and actionable safety guidance.

## Contain publication immediately

1. **Stop all new publication** and distribution of affected versions; **cancel queued publishing jobs**. An administrator may disable the guarded release.yml workflow in GitHub Actions while investigating and must also check **direct GitHub UI/API publication** permissions. Workflow YAML cannot prevent an authorized administrator publishing manually.
2. Have the appropriate provider or administrator **rotate/revoke** exposed tokens, signing credentials and publisher access using secure provider controls. Audit access and prevent replay. Never retrieve, display, or commit secret-bearing files to do so.
3. Do not install suspect builds, suppress scanner failures, bypass Quarantine or Gatekeeper, clear scan history or saved preferences, or silently replace an installed extension. Preserve the scan-before-open gate and its **fail-closed** behavior. Advise affected users to pause opening untrusted PDFs with a suspect build until a verified safe path is available.

## Withdraw affected distribution

Each action is **manual**, requires incident-lead approval, and must be checked from an **unauthenticated client**. Record before/after state and exact URLs.

| Distribution surface | Action and limitation |
| --- | --- |
| **GitHub Release**, only if one exists | Immediately change the affected release to **draft** with gh release edit vX.Y.Z --draft; after preserving private evidence, remove downloadable assets using gh release delete-asset vX.Y.Z ASSET --yes. Verify public release/asset URLs no longer serve the download. Remove affected links from official installation instructions. |
| **Git tag and source checkout** | **Never move or reuse a published tag.** A draft Release does **not** revoke Git clones, SHA-addressed objects, forks, cached files, or auto-generated tag archives. After preserving immutable SHA evidence, the incident lead may approve **deletion of the compromised tag**, with the decision recorded privately. Never force-push or rewrite main. Deleting a tag cannot erase distributed copies. |
| **GitHub Actions artifacts**, only if shared | Cancel the unsafe run, remove shared downloadable artifacts through authorized Actions administration, and verify exposed URLs are no longer available. CI artifacts are not approved public installers. |
| **Browser extensions**, only if actually published | Use the real publisher's emergency takedown, disable or delist process; contact the store/browser operator for emergency intervention if needed. Audit publisher-confirmed IDs and native-messaging allowlists. Delisting **does not necessarily uninstall** an installed copy; remote revocation is not guaranteed. |
| **macOS signed or notarized build**, only if distributed | Withdraw the download and request certificate/ticket remediation from Apple or the applicable issuer if warranted. Do not assume that revoking a signing identity or notarization ticket recalls existing installations. **No signing infrastructure** is currently enabled here. |
| **Source-only / manual installation** | Warn against the exact affected commit, archive and hashes; offer a separately reviewed clean revision only after verification. Previously cloned source cannot be remotely revoked. |

**Do not claim revocation by deleting only the Release page.** Git objects, mirrors and caches may remain accessible. Preserve affected version/tag/commit and SHA-256 identifiers in public warnings so recipients can identify compromised copies. The current distribution audit remains **NOT RELEASE READY** regardless of a withdrawal.

## Public warning and safe recovery

When credible exposure is identified, publish a **dated, non-exploit warning** using a GitHub Security Advisory or official project documentation and any distribution channels actually used. Explicitly mark affected versions, commits and hashes **withdrawn / do not install**; explain risk without private proof-of-concept details, provide a temporary safe alternative or advise users to pause use, and route private questions through [SECURITY.md](../SECURITY.md). Update notices as scope changes. Never promise remote removal of cached or installed copies or claim a replacement is safe before validation.

Before resuming any publication:

1. Identify and close the compromise route; audit access, rotate publisher credentials as applicable and review clean source and build provenance. Preserve incident evidence.
2. Prepare a **new version from a clean commit and new tag**, never a republished revoked tag or reused compromised asset. Recheck [release versioning](release-versioning.md), the [release gate](release-gate.md), required **critical CI**, source asset **SHA-256 checks**, and the **NOT RELEASE READY** distribution blocker. Do not bypass the blocker to restore service.
3. Independently verify native **scanner fail-closed** operation, **quarantine**, file **integrity** checks, migration and rollback, **native messaging allowlists** where applicable, and preservation of **saved browser** and PDF-handler **preferences** and protection selections. Compare the exact intended user-facing bytes with the reviewed candidate.
4. Reopen only a **separately approved** and tested channel. Update the advisory with precisely identified safe versions, removal and migration instructions, and notice that cached compromised copies remain unsafe.

Close the incident only after the release owner confirms withdrawal of links and publication of warnings, the incident lead signs off on affected identities and containment, and independent reviewers validate any replacement against its release gates. Record **remaining caches**, forks, non-removable installations, follow-ups and a private **post-incident review**. Do not claim universal deletion or revocation.
