# External PDF launch action inspection (opener-0288)

The standalone Enhanced inspection module `pdf_external_launch_actions.py` uses
strict parsing with maintained `pypdf==5.9.0` on immutable in-memory PDF bytes.
It identifies PDF actions capable of launching local programs or opening other
resources: `/Launch`, remote `/GoToR`, embedded `/GoToE`, `/URI`,
`/SubmitForm`, and `/ImportData`. It inspects file specifications, Windows
launch-command dictionaries, navigation destinations, and chained `/Next`
actions, without executing or dereferencing their external targets.

The bounded indirect-object walk includes catalog open actions, additional
action hooks, pages, annotations, outlines, form fields and unreferenced
indirect actions. This inspection is separate from automatic-action/JavaScript
inspection in concurrent PR #183; no script or command is evaluated.

Immutable results contain only counts and *safe category identifiers*. No
document content, command line, external URL, destination path, embedded
payload, or filename is exposed. `permits_open` is always false. Malformed,
encrypted, unsupported object-stream, oversized, and damaged-reference inputs
raise one fixed, path-free failure rather than an empty success result.

Limits: 16 MiB input, 4,096 indirect objects, 65,536 graph nodes, 512
external actions and 1,024 pages. These conservative limits apply **only**
to the inactive Enhanced stage, not the installed Built-in scanner. A future
sandboxed Enhanced pipeline must combine this inspection with every Standard
requirement, automatic-action checks and other structural validation before
profile activation. Nothing in this PR changes ClamAV, quarantine, clean
cache, preferences, or external application handoff.