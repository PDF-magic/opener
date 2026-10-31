# Opening Chrome-downloaded PDFs through the macOS scan gate (opener-0822)

This regression verifies that **real Chrome-download-manager PDF files** can
be checked by PDF Magic Opener's existing macOS scan-and-open gate. It uses
two sequential, isolated CI jobs because Chrome for Testing's renderer crashes
on both Apple Silicon and Intel GitHub-hosted macOS runners with Mach-port
rendezvous errors, before a PDF can be downloaded. A macOS Chrome download
itself is therefore **not** verified by this workflow.

## Step 1 — Real Chrome download on Linux

The Ubuntu job launches real Chrome for Testing against a disposable local HTTP
server. It verifies download start/completion events and exact bytes from both
`application/pdf` and `application/octet-stream` attachments. The Chrome
smoke script is unmodified for ordinary runs. For this workflow, the opt-in
`PDF_MAGIC_CHROME_HANDOFF_DIR` points to a new, empty temporary directory.

After Chrome saves and verifies both PDFs, the smoke script moves them from its
isolated browser profile into the handoff directory via same-filesystem rename.
No file is copied or opened. The job uploads those two actual downloads as a
short-lived GitHub Actions artifact; missing files fail the job.

## Step 2 — Real macOS quarantine and scan gate

The macOS 15 job depends on successful Chrome download validation, downloads
the artifact **from the same workflow run**, then confirms it contains exactly
the two expected files with identical valid fixture PDF bytes.

GitHub's artifact archive transport does **not** retain Linux or macOS extended
attributes. Accordingly the macOS test reads the actual
`com.apple.quarantine` value through `/usr/bin/xattr`, and when absent
attaches a deterministic marker **only to the disposable fixture file**. It
then requires the attribute's **exact bytes** and PDF contents to remain intact
through the actual production `scan_and_open` decision path.

For each downloaded PDF, the test verifies that a clean verdict and a cached
clean verdict would reach the configured handoff. It also verifies malware
detections, scanner errors and timeouts never reach the launcher. The external
scanner, application verification and final launch are replaced by deterministic
test doubles: no real PDF app is opened and no ClamAV process is invoked.

## Scope and limitations

The test establishes that Chrome-originated downloadable PDF bytes can pass
the macOS scan gate without stripping a macOS quarantine marker, and that
blocked scans do not authorize opening. It **does not** establish Chrome's
Gatekeeper tagging on macOS, macOS Chrome download behavior, a GUI opening
interaction, or cross-platform preservation of xattrs. Those claims require
separate real-browser macOS validation on an environment that supports Chrome
renderer processes.

No installed extensions, browser profiles, user downloads, opening preferences,
scanner policies, or production executables are modified. Temporary files are
created by the workflow and are removed with the runners.
