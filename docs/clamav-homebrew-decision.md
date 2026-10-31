# ClamAV distribution decision (opener-0957)

**Decision (2026-10-31): Retain Homebrew as the default provisioning route
for a missing ClamAV installation.** Do **not** make Homebrew a required
runtime dependency when an already installed scanner meets the existing
executable and version safety checks. Continue to use an external ClamAV
engine, not a copy bundled with PDF Magic Opener.

## Rationale and alternatives

- The existing `install-allow-and-open.sh` already installs `clamav`
  through Homebrew **only when** it finds no executable at its three
  supported paths. This preserves existing installations and avoids a
  second scanner distribution/update channel.
- Homebrew provides a macOS ClamAV package on supported Apple Silicon and
  Intel systems and supports upgrades through a maintained package manager.
  ClamAV's own installation guide identifies package managers as a
  convenient route for future updates.
- ClamAV also distributes a macOS installer that places its tools under
  `/usr/local/clamav`. The opener already recognizes the corresponding
  `/usr/local/clamav/bin/clamscan` path. Forcing that user to install
  Homebrew would add a dependency without improving the scanner gate.
- Bundling an engine is **not** selected here: it would introduce separate
  binary distribution, architecture coverage, dependency security updates,
  signing/notarization, and redistribution review. The project does not
  presently have that release/update mechanism. A vendor-bundled engine
  requires a separate evaluated proposal, not an implicit installer change.

This is a **default installation method**, not a recommendation to
automatically upgrade, uninstall, start `clamd`, change a user's ClamAV
configuration, or replace an existing compatible engine.

## Existing implementation contract

1. The installer checks
   `/opt/homebrew/bin/clamscan`, `/usr/local/bin/clamscan`, and
   `/usr/local/clamav/bin/clamscan` before its Homebrew fallback. It
   does not invoke Homebrew if an executable already occupies one of
   those locations. Its `-x` check is provisioning guidance, **not**
   the authorization to open a file.
2. At runtime, `scan-and-open.py` uses only the established candidate
   paths. It validates a regular executable, allows legitimate Homebrew
   symlinks, and checks the selected engine version against the currently
   supported ClamAV branches. An unsupported or unverifiable version
   fails closed; another binary is not silently selected to bypass it.
3. The mandatory signature freshness, malware scanning, file-integrity,
   quarantine, cache and destination checks remain authoritative. A
   package manager, executable path, or version alone cannot establish
   that a document is clean.
4. When ClamAV is absent and Homebrew is unavailable or installation
   fails, the installer must not claim success or bypass the scan gate.
   Detecting Homebrew availability and improving the missing-tool
   experience are separate checklist work, not part of this decision.

## Reconsideration triggers

Revisit the choice if an independently maintained, verifiably updated,
signed/notarized macOS scanner distribution can cover both architectures,
provide timely security patches and signatures, satisfy redistribution
requirements, and preserve the same fail-closed scan contract without
modifying users' existing installations. Until then, retain the existing
Homebrew fallback and permit compatible pre-existing non-Homebrew tools.

## Sources

- [ClamAV installation guide](https://docs.clamav.net/manual/Installing.html)
- [ClamAV upgrading guidance](https://docs.clamav.net/faq/faq-upgrade.html)
- [Homebrew ClamAV formula](https://formulae.brew.sh/formula/clamav)
