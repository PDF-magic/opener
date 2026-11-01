# Parser-timeout stress PDFs (opener-1045)

These three tracked, inert PDF 1.4 documents exercise pathological page-tree
traversal without using a large input file, untrusted scripts, attachments,
external URLs, or personal data. They are deterministic ASCII documents with
correct classic cross-reference offsets. The exact bytes are reproduced and
verified by `tests/pdf/parser-timeout-corpus.py`.

| Document | Structure | Expected bounded-parser outcome |
| --- | --- | --- |
| `wide-page-tree.pdf` | 1,024 `/Page` leaves in one `/Kids` array (page cap) | Returns metadata for 1,024 pages without granting opening permission |
| `deep-page-tree.pdf` | 64 indirect `/Pages` levels (depth cap) | Returns metadata for one page without granting opening permission |
| `cyclic-page-tree.pdf` | 48 `/Pages` levels ending in a back-reference to the root | Rejects before recursively flattening cyclic references |

The first two are valid stress controls that test whether costly-but-allowed
structures complete within the supervised worker's 30-second ceiling. The
third is an adversarial structure that must fail closed, rather than hang.
This corpus does **not** guarantee that a given parser runs for 30 seconds;
a fixed timeout failure is separately injected in tests without sleeping.

Run from the repository root after installing the pinned optional parser:

```sh
PYTHONPATH=. python3 tests/pdf/parser-timeout-corpus.py -v
```

CI registers this suite in the existing `scanner-tests` job. Documents are
inputs only, not scanner verdicts, opening authorization, profile activation,
or a reason to change saved user preferences.
