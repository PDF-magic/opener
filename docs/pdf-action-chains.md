# Passive PDF action-chain anomaly detection (opener-0449)

The optional Enhanced-inspection building block
`pdf_action_chains.inspect_pdf_action_chains(contents: bytes)` inspects
**real PDF action dictionaries with `/S` and `/Next`** throughout the
bounded indirect-object index, including orphaned actions, explicit
annotation `/A` links, and document-level action hooks. It does not
execute actions, evaluate JavaScript, resolve external URLs, or read
content from PDF streams.

It reports fixed, document-content-free anomaly categories:

- `cycle` — the same action is reached again on an active /Next path.
- `repeated_action` — a previously traversed action is referenced again.
- `competing_navigation` — two or more `/GoTo`, `/GoToR`, or
  `/GoToE` actions occur in one action sequence.
- `conflicting_form_operations` — `/ResetForm` is sequenced with
  `/SubmitForm` or `/ImportData`.
- `mixed_launch_navigation` — `/Launch` appears with navigation.
- `deep_chain` — a sequence exceeds eight action levels.
- `wide_chain` — an immediate /Next array contains more than eight actions.

`/Next` arrays are sequences, not exclusive-choice branches; the
inspector considers every action in such an array for potential
contradictions. Repeated navigation and form operations can be legitimate,
so these are **conservative signals for review**, not proof of malicious
intent or guaranteed semantic incompatibility. It does not attempt to
interpret scripts, event-specific conditions, or target contents. Ordinary
outline `/Next` links without action `/S` are not classified as action
chains.

The immutable `PDFActionChainInspection` reports the number of indexed
action dictionaries with /Next and sorted fixed finding codes. Its
`to_dict()` returns a detached, JSON-safe record that always contains
`authorizesOpen: false`. Neither PDF-controlled strings, paths, URLs,
targets nor raw script data can enter a result. A document with no
findings is **not** cleared to open.

Failures of strict parsing, uninspectable /Next links, malformed action
dictionaries, unsupported object streams, encrypted PDFs or resource
budgets produce a fixed, path-free error instead of an empty report.
Scanning is bounded to 4,096 indirect objects, 65,536 graph nodes,
512 action-chain roots, 32,768 chain visits, 64 levels of chain depth,
and 128 entries per /Next array. Depth beyond 8 and width beyond 8
are flagged before hard limits are reached.

This is a separate, inactive Enhanced-stage evidence collector. It does
not change `pdf_automatic_actions.py`, the installed ClamAV safety gate,
quarantine, cache, browser handoff, preference storage or profile
selection. Production use requires independent isolation and an
explicitly reviewed fail-closed policy.
