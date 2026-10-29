# Passive PDF form-action inspection (opener-0289)

The planned Enhanced protection stage provides
`inspect_pdf_form_actions(contents: bytes)` in `pdf_form_actions.py`.
It recognizes **/SubmitForm**, **/ResetForm**, and **/ImportData**
actions in indexed PDF objects, including form widgets, page actions, and
`/Next` chains. It validates required file targets, field selectors,
and action flags without submitting, resetting, importing, or opening
anything.

The inspector consumes immutable in-memory PDF bytes with strict
`pypdf==5.9.0` parsing. It has explicit byte, page, object, graph,
action, and field-selection budgets. Malformed, encrypted, unsupported,
or uninspectable input raises a fixed path-free error and does not yield
a clean verdict. Successful inspection returns only immutable counts
and action categories; it never returns submitted URLs, file targets,
field names, or form contents. A finding always has
`permits_open=False`, even when no form actions are present.

This stage is **not wired into the deployed scan-and-open path**:
the existing Built-in ClamAV gate, cache, quarantine handling,
preferences, and application handoff remain unchanged. The Enhanced
profile remains unavailable. The separate external-action inspector
already classifies the presence of /SubmitForm and /ImportData actions;
this stage validates the form-specific parameters without modifying
that existing detector.
