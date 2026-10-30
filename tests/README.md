# Python test organization

The Python regression suites live in `tests/<topic>/`, with lowercase kebab-case filenames that omit their directory prefix. For example:

- `tests/pdf/structure-parser.py` (previously `test-pdf-structure-parser.py`)
- `tests/maximum/sanitized-copy.py` (previously `test-maximum-sanitized-copy.py`)
- `tests/browser/registry.py` (previously `test-browser-registry.py`)

Use `python3 scripts/run-test.py tests/pdf/structure-parser.py -v` to run a suite from the repository root. Existing suites assume that their Python `__file__` is at the repository root and inspect adjacent scanner tools. The runner temporarily stages copies of the original scripts under their legacy root names, runs the selected test, then removes only the copies it created. It refuses to overwrite existing root files; this preserves the behavior of the tests without weakening scanner runtime paths.

`tests/manifest.json` is the checked-in, explicit old-to-new mapping. Add new suites directly to their topic folders and register them in the manifest until the compatibility runner is retired. CI runs `scripts/check-test-layout.py` to enforce naming, folder grouping, and absence of the legacy root files.

Swift tests remain separate: their source compilation and Xcode path assumptions require a distinct migration.
