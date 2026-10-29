# Required Maximum safe-copy handoff — opener-0320

When a future **trusted Maximum policy coordinator** requires a sanitized PDF, the original document must never be the browser/Preview launch target. The callable \`maximum_safe_copy_handoff.open_required_maximum_safe_copy(source_path, disposition=MaximumCopyDisposition.REQUIRED)\` implements this route without activating the unavailable Maximum profile.

The function reads one unchanged regular source PDF (never a final-path symlink), asks the established sanitized-copy pipeline to rasterize the PDF and independently rebuild pixels into a fresh passive PDF, and refuses a missing, invalid, identical-to-source, or incomplete copy. This uses the converter from opener-0313 and the second-stage active-content removal from opener-0315, rather than bypassing either. The original file is never passed to the launcher.

A successful candidate is written to a **new private 0700 temporary directory** as an exclusive **0600** \`safe-copy-<128-bit random hex>.pdf\`. Each filename is generated from 16 cryptographically secure random bytes, never a PDF field, source basename, timestamp or counter. The route invokes the **existing** \`scan-and-open.py\` gate with that separate path, using the dedicated `scan_and_open_generated_copy` gate from opener-0318: it verifies the saved bytes match the sanitizer offer, selects installed ClamAV, checks fresh signatures, forces a new scan even if a clean-cache entry already exists, and preserves file identity/integrity checks, quarantine, browser choice and verified launch handoff. The path of the original document is never sent to \`scan_and_open\`; a failed conversion, scan or viewer launch fails closed without falling back to the original. Failed staging and handoff remove the temporary copy. After a successful handoff the private temporary copy remains available to the selected viewer, subject to normal OS temporary-directory cleanup.

This is an explicit future Maximum-only routing primitive. It refuses any invocation without the exact trusted \`MaximumCopyDisposition.REQUIRED\` value. It does **not** select Maximum from user-supplied labels, interpret the original PDF as clean, run or replace the other required Maximum inspections, or change any installed scanning code. A coordinating Maximum implementation must complete the mandatory source checks and make the binding policy decision before calling this function. Maximum remains non-selectable until those controls are integrated and verified. The output must be scanned separately; the sanitized-copy offer itself never grants an opening verdict.

The Linux/macOS workflow tests mandatory separate routing, private output permissions, refusal of source symlinks or source mutations, non-retry of the original on scan/launch failure, fixed path-free diagnostics and unchanged Built-in scanner behavior. The installed scanner, preferences and other checklist implementations are untouched.

## Temporary-output symlink safety (opener-0536)

The route now stages via the existing `maximum_temporary_output` ownership
lease rather than a second independent path-based staging/cleanup routine.
The lease creates an exclusive `0600` file inside a private `0700`
directory and uses `O_EXCL | O_NOFOLLOW`; it records the original file and
directory identities. The handoff checks that lease immediately before and
after calling the mandatory generated-copy scanner. Symlinked, hardlinked,
replaced or reparented temporary outputs cannot be treated as successful
handoffs. A failed handoff only cleans up the exact owned inode through the
original lease; substituted links and unrelated files are never deleted.
The returned path still remains until the viewer is finished, rather than
being prematurely removed. Neither source selection, ClamAV, quarantine,
cache, preferences nor the nonselectable Maximum profile changes.
