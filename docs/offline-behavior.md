# Offline behavior (opener-1128)

PDF Magic Opener's **installed native Built-in scan gate can operate without
Internet access** for a PDF that is already present as a local, readable file,
provided the installed ClamAV executable, usable local signature databases,
and all other mandatory checks are available. The scan itself uses local
ClamAV; it does not fetch a PDF or refresh malware definitions on demand.
A disconnected network is **not** permission to skip scanning or open a file
without a trustworthy clean result.

## What works without a network connection

- Open an **already downloaded or otherwise locally available** PDF through
  the installed PDF Magic Opener handler (for example, Finder's Open With).
  The existing local malware scan, input-integrity and file-identity checks,
  macOS quarantine safeguards, and verified application handoff still apply.
  The installed post-scan PDF viewer must also be available. Whether the
  selected viewer can display a particular file offline is separate from the
  scan decision; PDF Magic Opener does not guarantee the viewer is offline.
- A previously verified clean result may be eligible for the existing
  **90-day SHA-256 clean-scan cache**. Cache reuse does **not** waive the
  mandatory signature-freshness, integrity, quarantine, or handoff gates.
  Changing signatures alone does not automatically rescan every cached file.
- Saved browser/application choices and other installed user preferences are
  not reset merely because the network is unavailable.

## What needs connectivity

- **Malware signature updates:** The separate FreshClam updater needs access
  to its configured update source. It does not run as part of a PDF scan.
  An unsuccessful offline update can retry the same updater once, but does
  not publish the incomplete staged database or advance the
  `last-successful-update` timestamp. Existing live signatures are retained
  if the staged update fails; a failed attempt does not certify their freshness.
- **Signature-freshness deadline:** The scanner requires a successful
  signature check within **48 hours**, as well as nonempty local `main` and
  `daily` databases. Opening is **blocked** when that timestamp or a
  mandatory database is missing, invalid, stale, or unverifiable, even on a
  previously cached clean file. Offline operation is therefore limited by
  the existing 48-hour gate; it does not extend that deadline.
- **Installation and downloads:** Obtaining Homebrew/ClamAV or updates, and
  downloading a remote PDF, can require a network connection. Browser-hosted
  **inline/embedded/remote PDFs are not automatically intercepted** by the
  native opener. Browser extension monitoring and native messaging scanning
  are not active, whether online or offline. Download a PDF locally first
  and explicitly route it through the installed PDF Magic Opener scan gate.

## If opening is blocked while offline

Use the established connection and signature updater when connectivity is
restored, then retry the local PDF normally. If ClamAV, a required database,
the file, or the selected viewer is unavailable, restore the missing
prerequisite before retrying. **Do not** backdate or overwrite update markers,
disable the scanner, strip quarantine, bypass a failed check, or switch to an
unverified fallback merely to open the document. The app does not treat a
network error, timeout, incomplete scan, or stale database as a clean verdict.

See [signature limitations](scanner/signature-limitations.md) for the
freshness/cache distinction, [scanner failure response](scanner/failure-response.md)
for denial policy, and [browser download monitoring support](browser-download-monitoring-support.md)
for inactive browser integration. The planned Standard, Enhanced, and Maximum
profiles do not change the installed Built-in offline behavior.

This page documents current behavior only; it does not change scan flags,
update scheduling, scanner policy, user choices, quarantine, or opening logic.
