# Troubleshooting PDF Magic Opener

This guide covers the **installed native macOS PDF-opening scan gate**, not universal
browser interception. Before troubleshooting, confirm that you are on
[macOS 13 or later](installation-prerequisites.md) and using a trusted, complete
PDF Magic Opener installation. **Only a completed clean ClamAV scan, current
signature checks, unchanged file identity, and a verified destination can permit
the native handoff.** A clean result is not a guarantee that a PDF is harmless.
Do not use an alternate viewer, disable Gatekeeper, strip quarantine, or edit
scanner flags to make a blocked file open.

## Common symptoms and safe next steps

| Symptom | What to check or do | Safety boundary |
| --- | --- | --- |
| **Installation cannot start, or a prerequisite is missing** | Confirm macOS 13+, Apple command-line tools, and an installed supported ClamAV binary. Read the installer's specific prerequisite message and the [installation prerequisites](installation-prerequisites.md). If needed, run `xcode-select --install` yourself before retrying the trusted `bash install-allow-and-open.sh` installer as your normal user. | Never run the installer with `sudo`, bypass its Homebrew consent, or assume passing a preliminary check proves the scanner works. |
| **ClamAV is missing or cannot initialize** | Verify installation using the trusted installer and the [ClamAV post-install checks](clamav-post-install-verification.md). A fresh, explicit scan attempt is required after restoring the prerequisite. | Missing or failed scanner means **blocked**, not clean; no fallback application is authorized. |
| **Malware signatures are unavailable, incomplete, or older than 48 hours** | Check **Settings → Updates** for the recorded last successful definition check. From the complete trusted installation source, use `update-malware-signatures.sh` or the existing explicit updater action; confirm success before starting a **new** scan. See [signature limitations](scanner/signature-limitations.md). | The timestamp alone is not a scan verdict. Never backdate freshness records, delete protections, or treat a failed update as successful. |
| **A PDF is blocked for detected malware or suspicious content** | Treat the warning as a stop: leave the file unopened and quarantined. Obtain a trusted replacement or ask the sender to verify the source. | Do not force-open, ignore the finding, remove quarantine, or relabel malware as a mere scanner failure. |
| **A scan fails, times out, is incomplete, or cannot inspect an encrypted file** | Read the fixed failure category, confirm scanner availability and current signatures, then retry only after the cause is resolved. If the PDF remains unscannable, leave it blocked. See [scanner failure responses](scanner/failure-response.md) and [unscannable quarantine](unscannable-quarantine.md). | No automatic retry, silent override, cached-clean result, or fallback browser is allowed; a timeout is **not** a clean scan. |
| **The document changed during scanning or was rejected as too large** | Save or obtain a stable complete local copy and submit that copy to a fresh scan. For size limits, consult the [scanner parameter decision](scanner/parameters-decision.md). | Do not increase or disable the active ClamAV limits or reuse a verdict for different bytes. |
| **Double-clicking a local PDF skips PDF Magic Opener** | In **Settings → General**, inspect **Default PDF handler**. To inspect the installed handler independently, run `python3 "$HOME/Library/Application Support/Studio/allow-and-open/pdf-handler-status.py"`. If you choose to change the association, use the explicit **Set as Default PDF App** action, or Finder's **Open With → PDF Magic Opener** for a single file. | The macOS **default PDF handler** is separate from the **post-scan browser** and the default web browser. Do not reset a user's association without permission. |
| **Scanning succeeds but the chosen PDF viewer is missing or refuses the handoff** | In **Settings → General → Default PDF browser**, choose an installed eligible viewer and verify **Default PDF browser saved.** If you have a custom app, use the [verified custom-application chooser](select-browser.md). Then initiate a new opening request. | A missing or unverified viewer must not cause silent browser switching. Preserve the previous saved preference on a failed selection. |
| **A PDF opened inside a browser without a PDF Magic scan** | Inline, embedded, and remote browser PDF routes are **not universally intercepted**. For the native workflow, download a complete local copy and explicitly open it with PDF Magic Opener. Read [unsupported routes](browser-unsupported-routes.md) and [inline scanning support](inline-pdf-scanning-support.md). | Browser extension installation or a download event is **not** proof of a completed native scan. |
| **An optional notification or scan-history entry is absent** | Review the relevant **General** notification setting and its macOS notification permission. Consult [failed-scan notifications](failed-scan-notifications.md); optional history is not on by default ([history decision](scan-history-default.md)). | Do not interpret a missing notification or history entry as proof of a successful or skipped scan. |

## Repair a damaged installation

From a **complete trusted source checkout**, use the interactive
`Repair Installation.command` action and type its required `REPAIR`
confirmation only if you intend to repair installed components. See
[Repair Installation](repair-installation.md) before proceeding.
This is not an automatic or privileged recovery method, and a failed repair
does not authorize opening a blocked document. The existing repair/install
path is designed to preserve the selected PDF browser, supported FreshClam
customizations, Finder Quick Actions, and other user preferences; do not
manually delete application-support directories or overwrite them as a
troubleshooting shortcut.

## Still not resolved?

Record only the **non-sensitive** symptom, macOS version, general operation,
and the fixed error/result category. Check [scan result vocabulary](../README.md#scan-result-vocabulary-section-13)
and [scanner failure policy](scanner/failure-response.md). If filing a
[GitHub issue](https://github.com/PDF-magic/opener/issues), do **not** attach
private PDFs, file paths, raw scanner logs, tokens, proxy credentials, or
other personal information. Unknown failures are **not** a reason to weaken
the existing scan gate, discard quarantine, or reset user customizations.
