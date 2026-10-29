# Scanner parameter editability decision (opener-0397)

**Decision: scanner parameters are not user-editable.** The installed PDF
opening workflow owns its ClamAV options, supported executable selection,
scan timeouts, and mandatory detection checks. Do not expose arbitrary
ClamAV flags, exclusions, alternative databases, or scan-limit overrides
in preferences or the command-line opening interface.

## Rationale and current contract

User-editable flags could suppress encrypted-file and limit alerts, exclude
untrusted content, or bypass mandatory scanning. The existing
`scan-and-open.py` builds the fixed arguments for PDF and non-PDF inputs,
and `scanner_argument_validation.py` rejects altered or additional options
before launching ClamAV. It passes file names after a literal `--`, with
no shell option expansion.

PDFs retain the existing `--max-filesize=0` and `--max-scansize=0`
options (subject to ClamAV's own engine limits) and a 30-minute timeout.
Other files retain 512 MB per-file and 1 GB total limits with a
three-minute timeout. Encrypted inputs, exceeded limits, scanner failures,
and inconclusive results remain fail-closed. This decision does not
change signature updates, malware handling, quarantine, or cache reuse.

The Advanced Scanning preferences page remains **read-only**. This is
different from supported user customizations: the selected PDF viewer,
scan-progress presentation, and notification preferences remain saved
and independently configurable. Protection previews do not switch the
installed malware gate.

## Implementation boundary

No new setting key, migration, scanner argument parser, command-line flag,
exclusion editor, timeout editor, or user-controlled scanner executable is
introduced. No existing saved settings are reset. Regression coverage
verifies that the fixed argument validator rejects overrides, that the
Advanced Scanning page cannot edit parameters, and that this decision is
visible in documentation and CI.

## When to reconsider

A future change would require a concrete user need, security review of
typed/bounded options, proof that mandatory checks remain enforced, and
dedicated integration and macOS UI coverage. Such changes belong in a
separate task, not opener-0397.
