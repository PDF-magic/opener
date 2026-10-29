# Displaying measured performance implications (opener-0332)

The Protection page now has a **measurement-gated** performance description
for each of its Standard, Enhanced and Maximum preview cards. A description
can include an approximate median and 90th-percentile **measured additional
inspection-stage time**, sample count, test platform and workload.

**Current state: no trustworthy performance comparison is available.**
The bundled `PDFMagicOpenerApp/protection-performance.json` includes no
measurements, so the page shows **"No representative performance measurements
yet."** for all three tiers. This is intentional and is not a fabricated
benchmark. The installed scanner still enforces only Built-in ClamAV; the
three preview cards remain unavailable as active policies.

## Source, method and limitations

The existing `enhanced_analysis_timing.AdditionalAnalysisTimer` measures
completed stage callbacks with a monotonic nanosecond clock without changing
scanner outcomes. The new
`protection_performance_evidence.PerformanceSampleGroup` requires **at
least five completed stage timing samples** using the same expected stages,
rejects missing, invalid, incomplete or failed runs, and computes the actual
median and nearest-rank 90th percentile. The
`build_report` function emits bounded, file-path-free measurement metadata
and no PDF contents, filenames, malware or opening verdicts. The Swift UI
loads an optional, versioned **bundled, read-only JSON** record and validates
the source scope, sample counts and positive finite durations before showing
any number. Missing or corrupt data fails to the unmeasured state.

Timing only the additional inspected stages is **not** a measurement of
end-to-end PDF-opening latency, the installed ClamAV scanner or the
performance of any active tier. The UI explicitly states this. Individual
CI test durations, configured timeout budgets, synthetic test clock ticks
and unimplemented profile stages are **not** representative data and must
never be populated as results. No relative speed multipliers or time ranges
are inferred.

To publish an estimate later, first instrument **real, fully supported**
stages on **representative, non-sensitive sample PDFs**, make multiple
completed runs on an explicitly described platform and workload, validate
the results through `PerformanceSampleGroup`, and record those actual
numbers in the bundled JSON. Rebuild and test the app. Any data for a
planned profile must be clearly described as an additional-stage prototype
measurement rather than actual enforced-policy performance. Never replace
an unavailable estimate with a configured timeout.

## Safety

Neither opening Preferences nor selecting a card performs a benchmark,
reads users' PDFs, writes telemetry, saves settings, or changes the scanner.
No persistent preferences, file associations, quarantine, cache approvals,
ClamAV execution or installed PDF-opening path are modified.

Run `python3 test-protection-performance-implications.py -v` plus the
existing scanner tests; the native macOS CI build verifies SwiftUI decoding
and inclusion of the JSON resource in the app bundle.
