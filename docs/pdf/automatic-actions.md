# Passive automatic PDF action inspection (opener-0286)

The optional Enhanced inspection module \`pdf_automatic_actions.py\` accepts
**in-memory PDF bytes** and parses them with the strict, pinned pypdf parser
from [opener-0283](https://github.com/PDF-magic/opener/pull/179).
It examines the catalog's \`/OpenAction\` and \`/AA\` hooks, document-level
JavaScript name trees (including \`/Kids\`), page \`/AA\`, annotation \`/AA\`,
and AcroForm field \`/AA\`. Action dictionaries are classified by their
\`/S\` name, and chained \`/Next\` actions are traversed.

Results are immutable, path-free, and contain only event categories, action
kinds and counts. Script sources, stream data, URLs, commands, field values,
filenames and PDF contents are **never returned or executed**. An ordinary
\`/OpenAction\` destination is counted separately from executable action
dictionaries. No annotation click action (\`/A\`) is counted as automatic,
because it requires an explicit user interaction.

Malformed, cyclic, unresolved, encrypted, oversized or unsupported PDF
structures, malformed JavaScript actions, dependency failures and inspection
limits return a fixed error rather than a false empty finding. Input is bounded
by the prerequisite parser to 16 MiB and 1,024 pages; additional limits are
4,096 dereferenced objects, 512 actions/field objects, 256 name-tree nodes,
2,048 annotations and a traversal depth of 64.

This **does not activate Enhanced** or change the installed ClamAV gate,
quarantine, cache, browser handoff or preferences. In particular, these
metadata findings do **not** provide a clean verdict or authorize opening:
\`permits_open\` is always false. A production Enhanced integration must
first validate the entire action graph, use isolated time/memory-bounded
workers, and define appropriate block/allow decisions through the existing
fail-closed policy. Passive inspection alone is not a sandbox.
