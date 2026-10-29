# Passive automatic external-request identification (opener-0460)

The optional Enhanced inspector
`pdf_automatic_external_requests.inspect_pdf_automatic_external_requests(contents)`
correlates external-request *intent* with PDF automatic action hooks. Existing
`pdf_automatic_actions.py` finds automatic action types, and
`pdf_suspicious_urls.py` finds URL risks; neither by itself proves that a
URL-bearing action is triggered automatically. This inspector checks that
specific relationship while remaining strictly passive.

## What is counted

- **Document-open requests:** explicit `/URI` actions or remote targets
  reached through the document catalog `/OpenAction`, including their
  chained `/Next` actions and `/Next` arrays.
- **Event-triggered requests:** the same external action kinds reached through
  catalog, page, form-field or annotation `/AA` action dictionaries. Their
  events can require closing, saving, printing, entering a page, moving a
  pointer, focusing a field, or typing; the report does **not** claim that
  they necessarily execute at document open.
- **External-request kinds:** explicit `/URI` navigation; a
  `/SubmitForm` or `/ImportData` with a remote target;
  `/GoToR` or `/GoToE` with a remote document URL; and
  `/Launch` with a remote URL target. The last category is *possible
  external access*, not proof the PDF viewer makes a network request.
  Recognized URL file specifications (`/FS /URL`) are supported.
- A local file target, ordinary internal destination or a click-only link
  annotation `/A` is **not** misclassified as an automatic network request.
  A clickable annotation with an automatic event hook `/AA` is counted as
  event-triggered only.

JavaScript action bodies are never executed, token-matched or assumed safe.
A `/JavaScript` reached from an inspected hook increments the separate
`unassessedScriptCount`. Dynamically generated requests from scripts are
**not identifiable as confirmed requests** by this detector, so zero explicit
requests does not prove a PDF cannot access the network. Other unsupported
viewer behaviors similarly require additional independent inspection.

## Evidence and safety

`PDFAutomaticExternalRequests` is immutable and returns
`documentOpenRequestCount`, `eventTriggeredRequestCount`,
`unassessedScriptCount`, fixed `requestKinds` and `triggerContexts`,
and `authorizesOpen: false` in a detached JSON-compatible record.
Actual URLs, form data, filenames, user-controlled labels, script text,
paths and parser errors never enter the result.

The shared strict PDF parser enforces its structural and input limits. The
action walk additionally bounds the number of actions (512), indirect
references (4096), action/field depth (64), fields (512) and annotations
(2048). The existing URL parser validates candidate addresses without
resolving DNS. Any malformed, encrypted, uninspectable or resource-exhausting
input raises one fixed content-free error and does not return a clean report.

This is evidence of a **potential automatic external request**, not evidence
that traffic occurred, proof of maliciousness, or permission to open.
It does not change the installed ClamAV scanner, signature updates, quarantine,
clean cache, browser handoff, profile selection, or user preferences.
The Enhanced stage remains inactive until separate isolation and policy
integration are complete. CI tests generated PDF action graphs alongside
existing automatic-action, suspicious-URL, and form-action regressions.
