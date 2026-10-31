# Webpage-generated PDF verification (opener-0807)

The existing headed **Brave Stable** smoke test now serves a disposable HTML
webpage on loopback. That webpage assembles a valid PDF **in JavaScript** at
runtime, creates an `application/pdf` **Blob** and opens its own `blob:` URL.
The HTTP server never returns the generated PDF bytes. The test requires
Brave to navigate to the generated Blob URL, observe its actual browser-owned
PDF viewer frame, and avoid downloads; merely creating a URL is insufficient.

A deterministic unit test executes the webpage's PDF generator in isolation,
checks the PDF signature and cross-reference offsets, and confirms the
navigation uses the newly created Blob. This is covered by the shared Node
test suite. The existing Brave CI job exercises real browser behavior through
a temporary profile and virtual display without changing any installed browser
or **user preferences**.

**Security boundary:** Rendering a webpage-created PDF does **not** prove a
ClamAV **scanner** verdict, native scan-before-open protection, interception,
or authorization to open a user document. The extension background remains
inactive, no new browser permissions are granted, and scanner safety gates
remain unchanged. The result establishes the behavior of this tested Brave
version on an isolated Linux profile, not all dynamically generated or
downloaded PDFs across Chrome, Firefox, Edge or Safari. Embedded iframe PDF
tests belong to opener-0805, not this task.
