# Protection profile dependencies and activation blockers (opener-0338)

The native Protection settings page offers **preview-only** Standard, Enhanced
and Maximum cards. Each card now explains why its **effective** policy cannot
be activated. Choosing a preview remains harmless, in memory, and does not
change saved preferences or scanner behavior.

- **Standard**: the named Standard policy is not integrated with the installed
  PDF scan gate. Its baseline ClamAV checks exist in the separate **Built-in**
  active policy, but that is **not** evidence that the planned Standard
  selection has become an available engine.
- **Enhanced**: the required PDF structure validation engine is **planned**,
  not integrated as an enforceable scan stage. Baseline checks remain mandatory.
- **Maximum**: required PDF structure validation and isolated behavior
  analysis are **planned**, not integrated as mandatory engines. Maximum must
  inherit all Enhanced requirements, not silently skip unavailable checks.

Every missing mandatory check listed in the structured
`protection_policy_definitions.PROTECTION_POLICIES` contract appears as an
unavailable dependency on the selected tier's detail view. Cards explicitly
mark activation as unavailable and do not contain a policy activation action.
Their accessible hints warn that activating the named level is blocked. These
labels describe *known integration state*, not a live probe of installed
scanner executables, files or user PDFs.

The existing `effective_protection_policy.resolve_effective_policy` refuses
**all** `selectedProtectionProfile` values other than `built-in` with
`UnsupportedEffectivePolicy`. That refusal is retained and tested for
Standard, Enhanced and Maximum. The standalone opener retains its own scanner
readiness, signature freshness, file-integrity, quarantine and verified
handoff checks; this task never claims a selectable planned policy is safe
merely because a separate module or binary happens to be present.

`test-unavailable-protection-dependencies.py` checks the status of each
mandatory control, the displayed reasons, no persistent settings writes, and
the existing fail-closed effective policy resolution. The Linux scanner CI job
runs this test; the required macOS build compiles the native view. This task
does not add automatic retries, downgrade blocked profiles, change an existing
installation's saved values, or authorize opening any PDF.
