# Dependency licensing review (opener-0959)

The offline reviewer `python3 scripts/check_dependency_licenses.py` checks the
versioned Python dependencies used in GitHub Actions and
`requirements-enhanced-pdf.txt` against the evidence-backed inventory in
[dependency-licenses.json](dependency-licenses.json). It also checks that the
WebExtension remains dependency-free, that the project retains its AGPLv3
license, and that the separate ClamAV package-manager installation route
is still present. It fails closed for unreviewed packages, pin changes,
missing license records, or unexpected installer arguments. CI runs both
the checker and synthetic mutation tests before installing optional
test-only libraries.

| Dependency | Reviewed licensing | Use |
| --- | --- | --- |
| ClamAV / FreshClam | GPLv2 | External executable installed by Homebrew, not bundled with the application |
| pypdf 6.21.4, 5.9.0 | BSD-3-Clause | Enhanced requirements pin 6.21.4; legacy portable CI jobs still pin 5.9.0 |
| Pillow 11.3.0 | MIT-CMU | Optional sanitization tests |
| cryptography 46.0.4 | Apache-2.0 OR BSD-3-Clause | Optional validation tests |
| PyMuPDF 2.0 / MuPDF | AGPLv3 or Artifex commercial license | Optional isolated Maximum renderer |

**Distribution requirements:** retain the required license and attribution
notices of each dependency, satisfy corresponding-source and downstream
obligations when distributing copyleft binaries, and review the license
notices of dependencies bundled in wheels or ClamAV packages. The
application's own AGPLv3 `LICENSE` does not replace GPLv2 ClamAV
notices or other third-party licenses. ClamAV specifically lists
third-party code with separate license terms, including runtime-loaded
UnRAR components: see [upstream licensing](https://github.com/Cisco-Talos/clamav#licensing).
For PyMuPDF, see [Artifex's two licensing routes](https://pymupdf.io/licensing).
The repository does not redistribute the Homebrew-managed ClamAV binary;
if packaging changes to embed it, its notices and corresponding source
requirements must be independently satisfied before shipping.

This is a **dependency declaration review**, not automatic verification
of installed binary provenance, the effective license of every transitive
package, or legal clearance for any specific distribution. Any upgrade,
new dependency, vendoring or redistribution needs a fresh upstream review
and necessary notices before changing both the allowlist and inventory.
The check performs no downloads, executes no untrusted packages, and does
not alter the scanner's required ClamAV or signature-freshness gates.
