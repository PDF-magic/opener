# Source lint checks

The [Source lint workflow](../.github/workflows/source-lint.yml) runs on pull
requests, merge queues, and pushes to `main`. It is separate from the existing
scanner, parser, security, packaging, and macOS integration test suites.

- **Python:** Ruff 0.14.3 checks the repository's Python source and tests for
  syntax errors (`E9`), invalid assertions and comparison constructs (`F63`),
  invalid control flow and imports (`F7`), and undefined or unbound names
  (`F82`). The targeted error rules avoid imposing an unrelated formatting
  rewrite on existing source.
- **WebExtension JavaScript:** Node.js 22 parses checked-in `.js` and
  `.mjs` files under `extensions/webextension` without executing extension
  code. Generated `dist` output and installed `node_modules` are excluded.
- **Negative controls:** The workflow checks that Ruff rejects an undefined
  Python name and Node rejects malformed JavaScript, so miswired checks do not
  silently pass.

Run the same non-mutating checks locally:

```sh
python3 -m pip install 'ruff==0.14.3'
ruff check --select E9,F63,F7,F82 .
find extensions/webextension -type f \( -name '*.js' -o -name '*.mjs' \) \
  -not -path '*/node_modules/*' -not -path '*/dist/*' -print0 \
  | xargs -0 -r -n1 node --check
```

These checks do not reformat files, load PDFs, invoke ClamAV, change scanning
policy, or modify user preferences. They complement rather than replace the
existing functional and security CI checks.
