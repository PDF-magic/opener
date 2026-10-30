# Three protection cards in Settings (opener-0327)

The native **Preferences → Protection** page now presents three distinct
clickable cards: **Standard**, **Enhanced**, and **Maximum**. Each has an
accessible name, keyboard-operable SwiftUI button, visual selection outline,
and short explanation. Selecting a card displays its detailed description
in a single shared panel. The selection is in-memory only; selecting a second
card replaces the preview of the first. The page scrolls with larger text.

## Important policy distinction

The three cards are **selectable previews, not selectable enforced policies**.
The currently installed PDF opener supports **Built-in ClamAV scanning**,
which remains the active scan policy. All three named tiers remain planned and
non-selectable for enforcement in `protection_profiles.py`. Their status is
visible directly on every card, in the explanatory text, and in accessible
VoiceOver values and hints. Selecting a preview does not save a setting,
activate incomplete inspection, start a scan, override a failed scan, open
a PDF, or change any browser.

This separation is intentional. The user interface can be developed and
tested now without claiming that Standard, Enhanced, or Maximum already
enforce safety promises that depend on separate checklist tasks. Enabling
and persisting an actual scanner policy requires a separately reviewed
implementation of those complete protection tiers and safe scanner-side
application of that choice. The future task must update the UX truthfully
when those prerequisites are met; it must not reinterpret the current
preview state as an active setting.

The existing malware-scanning, unsafe-file and verified-handoff sections
are preserved. No changes to ClamAV, signature freshness, quarantine,
caching, verified PDF/browser handoff, persistent preferences, or the
installed standalone handler are made by this task.

## Verification

`python3 test-protection-settings-cards.py -v` checks the three named
cards, shared selection, accessibility, visible active-policy truth, lack of
persistence and scanner writes, retained settings sections, and the native
target. Existing main preferences and technical-help tests now explicitly
allow the UI-only preview buttons while continuing to block scanner,
filesystem and preference mutation. The `scanner-tests` GitHub Actions
job runs these checks and the macOS application build compiles the view.

## Maximum PDF capability-loss preview (opener-0552)

Selecting the **planned Maximum** card shows an accessible, read-only heading
**“PDF capabilities that may be removed”** followed by a fixed explanation.
A future rasterized safe copy may lose selectable/searchable text, clickable
links, interactive form fields, annotations/comments, embedded attachments,
metadata, and scripts or other active PDF actions. Flattening can invalidate
digital signatures and change the appearance of some visual details; OCR is
not restored. Users should retain the untouched original if they need those
features. A generated copy is not a malware-clean verdict and requires a
separate fresh scan before opening.

The warning is scoped to the Maximum preview, not Standard/Enhanced and not
a fabricated scan result for any PDF. It shows no PDF-controlled strings,
source path, or filenames. Selecting the preview neither enables Maximum nor
converts, saves, scans, opens, or modifies any document. The separate
original-versus-generated comparison (opener-0551) can appear alongside
this explanatory notice without duplicating its identity controls.

The existing `test-protection-settings-cards.py` regression, executed by
the required `scanner-tests` job, verifies the warning's content,
Maximum-only gating and accessible display. The native `macos-build` job
compiles the SwiftUI view. Current Built-in ClamAV protections, mandatory
scan/handoff boundaries, quarantine and customized preferences are unchanged.
