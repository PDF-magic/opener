# Save Sanitized PDF interface action — opener-0554

The future Maximum protection UI exposes a **Save Sanitized PDF** action
through `maximum_save_sanitized_pdf_action.available_save_sanitized_pdf_action(offer)`
only for a strictly verified, in-memory, rasterized
`SanitizedCopyOffer`. It returns a fixed, path-free label, generated-copy
identity, mandatory conversion warning, required user action and destination
selection, fresh-scan requirement, and explicit statements that this action
neither authorizes opening nor permits overwriting.

After an affirmative user click, a trusted coordinator calls
`save_sanitized_pdf_action(offer, user_requested=True, choose_destination=...)`.
The destination selector is presented **only after** the offer passes
verification; cancelling is a no-op. The selector can be backed by the
separate native Save destination dialog from opener-0545 (PR #345).
This task does not duplicate that dialog. A selected pathname is never
trusted as permission to write, overwrite, scan less thoroughly or open.

The action delegates to `maximum_save_sanitized_copy.save_sanitized_copy`
from opener-0544 (merged PR #347). That gate independently revalidates the
offer, stages a private owned temporary copy, requires the installed ClamAV
engine's **fresh non-cached scan** and file-integrity checks, and creates
the permanent output exclusively without following or replacing existing
files or symlinks. Failed attempts cannot open the source document; success
does not launch a PDF viewer. The original PDF is untouched.

The **Protection → Maximum** preview displays the labeled, accessible
SwiftUI button through `MaximumSanitizedPDFSaveControl`. The component
takes a trusted verified-offer availability flag and a supplied callback;
it enables the button only when **both** are available, then invokes the
callback on an explicit click. In today's installed Built-in-only Settings
view there is **no verified per-document Maximum offer or integrated
coordinator**, so the button is deliberately disabled with an explanation.
A chosen Maximum *preview* is never a scanner verdict or a generated PDF.
A future coordinator must supply both the real verified offer and save
handler; this PR does not prematurely enable Maximum.

The portable CI suite tests consent, offer validation, native-picker
cancellation semantics, delegation to the existing secure save gate,
exclusive file persistence, path-free failures and unchanged original.
The existing `test-protection-settings-cards.py` asserts the real native
control's accessibility, availability gating and disabled installed state.
The macOS app build compiles the SwiftUI component. No scanner, setting,
signature database, quarantine behavior or viewer handoff is changed.
