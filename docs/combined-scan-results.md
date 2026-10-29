# Combined ClamAV and structural findings (opener-0479)

The combined scan report keeps two independent evidence sources together without
blurring their meanings:

- The terminal scan status records whether the existing scan request completed
  cleanly, detected malware, failed, timed out, was cancelled, or was stopped for
  another required check.
- The ClamAV section carries the effective policy identifier and only validated
  signature names. It never includes scanned paths, raw output, or diagnostics.
- The structural findings section uses the explainable schema-version-2 contract,
  retaining expected-stage order, missing/incomplete stages, finding identifiers,
  bounded locations, and fixed handling explanations.

The public entry point is combine_scan_results in combined_scan_results.py. It
requires a validated ScanResultStatus, ScanResult, and StructuredAnalysisFindings.
Detection names are checked again before serialization, duplicates are rejected,
and more than 256 names fail validation rather than being silently truncated.
A clean status with detection names is contradictory and is rejected. A
malwareDetected status still blocks when no safe signature name could be parsed.

The top-level requiresBlock signal is true if the scan status is not clean,
ClamAV detection evidence is present, or the explainable structural report
requires blocking. Neither source can override the other. A structural finding
cannot downgrade a ClamAV detection, and a clean ClamAV result cannot erase
incomplete structural inspection or a blocking structural finding.

Every combined report has authorizesOpen set to false, including a report whose
evidence does not require blocking. This is an evidence aggregation contract,
not a new scan gate or a clean verdict. The installed scan-and-open.py path,
quarantine preservation, file-integrity verification, effective Built-in policy,
and non-selectable Enhanced profile remain unchanged.
