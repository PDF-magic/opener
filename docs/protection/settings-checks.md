# Display included checks for each protection level — opener-0331

The three selectable **preview cards** from opener-0327 now explicitly list their included required checks. The card for Standard, Enhanced, or Maximum displays the current baseline controls by name; planned checks appear only in levels where the structured policy includes them. A separate optional label distinguishes optional checks from required checks. Selecting a preview card reveals the individual check explanations and availability statuses, including accessible labels that work with large text.

The underlying, non-executable policy contract in \`protection_policy_definitions.py\` remains authoritative:

| Planned level | Required checks | Optional planned checks |
| --- | --- | --- |
| Standard | ClamAV scan gate, signature freshness, file integrity, fail-closed verified opening (all current Built-in safeguards) | PDF structure validation |
| Enhanced | The four current safeguards plus **planned required** PDF structure validation | Isolated behavior analysis |
| Maximum | The four current safeguards plus **planned required** PDF structure validation and **planned required** isolated behavior analysis | None |

**Current** means already enforced by the *installed Built-in ClamAV scanner*, not that a planned tier is selectable. **Planned** means the complete tier is not active, even when individual analysis components have been implemented. This checklist task changes only comparison text; it does not activate a tier, persist a card selection, run scans, open files, or change the user's PDF application, quarantine rules or existing preferences.

The SwiftUI catalog uses the exact six structured policy-control IDs. \`test-protection-settings-checks.py\` cross-checks every tier's required/optional control IDs and availability labels against the Python policy schema. It also checks the in-card summaries, expanded accessible detail, non-mutating UI, original settings sections and native build wiring. The Linux \`scanner-tests\` CI runs the contract test, and macOS CI compiles the real SwiftUI settings view.

The new work is stacked on opener-0327 until those preview cards merge; it deliberately does not recreate or republish that PR.
