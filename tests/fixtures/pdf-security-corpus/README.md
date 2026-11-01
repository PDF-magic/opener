# PDF security corpus expected results (opener-1047)

`expected-results.json` records an explicit, test-only expected result for **each
currently established fixture**, including in-memory generators, tracked truncated
PDFs, empty inputs, and misleading filenames. Entries identify the collection and
fixture, the expected passive evidence, and `authorizesOpen: false`.

**Do not interpret these as live scanner verdicts.** The six baseline
`simulatedScannerOutcome` values are injected test stubs, not detections made by
ClamAV. A valid PDF, a parseable oversized document, or a synthetically signed
PDF does not grant permission to open it. Tests must not execute PDF actions,
launch external resources, run the live scanner, or treat a signature as trust.

When adding fixtures to an existing collection, record their individual expected
results and supported evidence here. New collection families must also be added
to the independent enumerator in `tests/pdf/expected-fixture-results.py`.
The test checks completeness and metadata agreement; the existing corpus-specific
tests remain responsible for inspecting each fixture's actual parser behavior.

Run from the repository root after installing the pinned optional parser:

```sh
PYTHONPATH=. python3 tests/pdf/expected-fixture-results.py -v
```

The manifest lives inside the security corpus directory so the existing
`export-ignore` rule prevents it and hostile test PDFs from entering ordinary
source-release archives. It is only used for tests, not shipped as a scanner policy.
