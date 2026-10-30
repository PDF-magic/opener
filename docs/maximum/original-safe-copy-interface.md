# Original PDF and generated safe copy in Maximum preview (opener-0551)

The existing **Protection** settings page offers a read-only comparison
only when the user previews the planned **Maximum** tier. It identifies:

- **Original PDF:** the unchanged source document. A required sanitized-copy
  handoff must never launch the original as a fallback.
- **Generated safe copy:** a separate PDF reconstructed from rasterized
  page images, **not** the untouched original. Its appearance and content
  can change, including loss of selectable text, links, forms and digital
  signatures. Before any opening it requires a separate fresh scan.

The two accessible labels and explanations appear together with an explicit
notice that this is an illustrative preview; **no document is converted,
scanned, opened or saved here**. The interface never claims to show a real
document's scan status and has no filename- or path-derived labels. The
underlying optional Maximum offer and handoff retain their trusted
`generatedContent` and `isUntouchedOriginal=false` identity contracts,
which future document-specific interfaces must use rather than inferring
origin from a temporary path or the selected tier.

Maximum remains unavailable for enforcement. The existing Built-in ClamAV
scanner, fail-closed opening, user preferences, original files and safe-copy
retention/cleanup are unchanged. The already required
`test-protection-settings-cards.py` CI test covers display labels, preview
gating, accessibility, immutable identity metadata and scanner isolation;
the existing macOS build checks native SwiftUI compilation.
