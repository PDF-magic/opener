# Enhanced as a conditional new-install recommendation (opener-0333)

**Current verdict: not supported by testing.** Enhanced is a *candidate* for a
future recommended default on **new installations**, but the application must
not identify it as the actual recommended default yet.

The installed scanner currently enforces only **Built-in ClamAV**, and the
named Standard, Enhanced and Maximum profiles are non-selectable previews.
`protection_policy_definitions.py` still describes required Enhanced PDF
structure validation and optional isolated analysis as **planned**.
The shared reference-PDF suite in `test-reference-pdf-profiles.py` explicitly
rejects all three named policies. Individual Enhanced inspector tests and
timing instrumentation do **not** establish complete, production-integrated
protection or an adequate end-to-end performance comparison.

## Evidence required before changing the verdict

A future change can name Enhanced as the recommended *new-install* default
only after it separately verifies all of the following:

1. **Activation and safety:** Every required Enhanced inspection is integrated
   into the installed scan gate, its failures/timeouts block opening, and no
   previously mandatory ClamAV, signature, file-integrity, quarantine, or
   verified-launch checks can be bypassed.
2. **End-to-end comparative validation:** Run Standard/Built-in and the
   executable Enhanced policy over the same representative benign, malicious,
   malformed and resource-limited PDFs. Confirm correct fail-closed outcomes
   and no unacceptable false positives or regressions, on supported macOS
   installations (not just mocks and preview metadata).
3. **Measured user impact:** Benchmark actual extra analysis time, resource
   use and reliability under the new-install workflow; define and satisfy
   documented acceptance thresholds rather than inferring performance from
   proposed budgets.
4. **Reviewed rollout:** Only after the evidence is accepted should a separate
   implementation activate the profile and select it as the default **only
   for new installations**, keeping existing explicitly saved settings intact.

The Protection screen now visibly explains why Enhanced is **not yet
recommended** and what would support its future selection. This is static,
truthful explanatory content, not a switch, saved preference, or policy
activation. The current installation and all pre-existing user preferences
remain unchanged. No scan gate, UI card-selection semantics, default
migration, browser, quarantine or malware scanner behavior is changed.

`test-enhanced-new-install-default.py` locks the absence of unsupported
recommended/default labeling, verifies inactive Enhanced requirements,
checks the mandatory effective Built-in policy and the independent preview
UI, and runs on Ubuntu/macOS in dedicated GitHub CI. The native macOS build
continues to verify compilation.
