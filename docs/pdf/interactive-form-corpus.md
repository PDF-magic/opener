# Interactive-form PDF security corpus (opener-1039)

`interactive_form_corpus.py` generates three deterministic, in-memory,
one-page PDF documents with genuine interactive **AcroForm** structures.
The fixtures are not static drawings masquerading as forms.

| Corpus document | Form field | Structural coverage |
| --- | --- | --- |
| `acroform-text` | `/Tx` | Text field with a value and widget appearance |
| `acroform-checkbox` | `/Btn` | Checked state, `/AS`, and `/Off`/`/Yes` appearances |
| `acroform-choice` | `/Ch` | Combo-box flag, options, selected value, and widget appearance |

Every sample has a catalog `/AcroForm /Fields` entry, a real `/Widget`
page annotation, matching `/Parent` and `/Kids` links, and an inert
appearance stream. Tests use a strict parser to verify these details and
confirm that the existing passive feature inspector reports
`interactiveForms` while **never** authorizing the document to open.
They also verify that no form actions, JavaScript, XFA, external calls,
or executable attachments are introduced.

This corpus is separate from the six clean baseline documents and from
the Maximum form-fidelity tests. It does not feed an installed scanner,
change ClamAV or quarantine behavior, select a protection profile, or
modify user preferences. It uses only synthetic fixture values; the
PDFs are never opened in a viewer.

Run from the repository root:

```sh
PYTHONPATH=. python3 tests/pdf/interactive-form-corpus.py -v
```

GitHub Actions runs the same check on relevant changes and on demand.
