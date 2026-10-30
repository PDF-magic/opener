# Python regression tests

The Python regression tests are grouped by subsystem in `tests/<topic>/`. All
test filenames use lowercase hyphen-separated names without repeating their
folder prefix; for example `tests/pdf/structure-parser.py`.

Run tests directly from the repository root:

```sh
PYTHONPATH=. python3 tests/pdf/structure-parser.py -v
PYTHONPATH=. python3 tests/configuration/loading.py -v
```

Setting `PYTHONPATH=.` keeps imports of the root-level production modules
available while each test locates fixtures and source files from the repository
root. No temporary copies of tests are written into the root.

CI checks the test layout and runs the tests using their actual paths.
Swift/Xcode regression tests remain in their existing locations.
