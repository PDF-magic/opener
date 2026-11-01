# Reproducible unsigned release candidates (opener-1136)

The build produces **unsigned, inactive browser-extension candidate ZIPs**.
It does **not** create a signed, installable, or public release. The
[distribution audit](browser-extension-distribution.md) remains
**NOT RELEASE READY**, and the [release gate](release-gate.md) still blocks
publication until the independent signing and distribution prerequisites pass.

## Build

Install Python 3.11+ and Node.js 22, then run from the repository root:

    python3 scripts/build_reproducible_release.py --output-dir /tmp/pdfmagic-candidates

Use a previously nonexistent output directory. The command copies only an
explicit allowlist of reviewed manifests, inert assets, icons, and package
scripts into **two separate temporary trees**. It runs the existing Chrome
and Firefox validators and ZIP packagers in each tree, verifies each archive's
ten allowed entries, fixed timestamps, and manifest, and compares complete
ZIP bytes across the independent builds. Only then are both versioned ZIPs
and a deterministic SHA256SUMS written. A divergent build fails, and an
existing destination is never overwritten.

The copy allowlist excludes test/security fixtures, private keys, signing
material, unrelated source, and stale dist directories. The build does not
install applications, change any PDF associations, scan a user's document,
modify user preferences, or touch the installed scanner or quarantine policy.

The dedicated PR, merge-queue, and main CI job runs this verification and
retains its unsigned ZIPs and SHA256SUMS as **CI evidence only**. A reviewer
can repeat the command at the same commit in a second clean checkout using
Node.js 22 and compare the SHA256SUMS file.

The Firefox output still has its development-only example.invalid ID and
requires Mozilla signing; Chrome distribution requires store publisher
approval. Signed Safari/macOS archives and their toolchain-dependent
reproducibility are outside this task and require separate Apple signing
and notarization work. No unsigned artifact may bypass release readiness.
