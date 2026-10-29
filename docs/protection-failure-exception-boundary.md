# Keep scanner failures separate from feature exception requests (opener-0344)

The PDF Magic Opener does **not** support user-approved exceptions that
waive mandatory PDF protections. The separate opener-0342 policy task
([PR #229](https://github.com/PDF-magic/opener/pull/229)) defines the
unsupported-exception decision. This task does not add an allowlist, prompt
to override a blocked PDF, or enable any planned protection profile.

## Two distinct blocked outcomes

`protection_failure_exception_boundary.report_protection_block()`
provides an optional, read-only diagnostic contract for a future caller.
It does **not** change the installed scanner or infer a clean scan result.

* A scanner **initialization failure, process failure, timeout, incomplete
  result, or unknown failure token** is always reported as
  `origin="scannerFailure"` with the unchanged, specific terminal
  `ScanResultStatus` and fixed, private-data-free
  `scanner_failure_policy` message. A claimed feature approval is ignored.
* A user-requested **feature exception** *without* a scanner failure is
  reported as `origin="featureExceptionRejected"`,
  `scanStatus=null`, with a fixed rejection message. It must not be
  presented as a malware detection, scanner failure, successful scan, or
  approved exemption.
* No report when neither is supplied means **no diagnostic from this
  component**, not permission to open a file.

Both reports have `authorizesOpen=false` and
`userExceptionApproved=false`. The immutable contract rejects forged
clean/malware verdicts and cross-category messages. It never reads or logs
an exception request, filesystem path, PDF data or scanner stderr.

## Existing safety behavior remains authoritative

`scan-and-open.py` still checks ClamAV, signature freshness, file integrity,
quarantine and its verified application handoff. A failed or incomplete
scan never becomes clean because of feature metadata or a proposed
"approved" exception. This classification helper does not wrap, replace
or monkey-patch the production scanner, alter preferences, save overrides,
affect the verified cache, or establish new scanning behavior.

The CI regression
`python3 test-protection-failure-exception-boundary.py -v`
exercises all authoritative scanner failure kinds, forged exception claims,
malicious/opaque requests, immutable status validation and a real scan gate
invoked with a simulated failing subprocess. Other scanner and native
application jobs remain mandatory.
