# Test PDFs inside embedded frames (opener-0805)

The existing `pdf-iframe.js` classifier identifies URL-path candidates; it
does **not** prove a browser rendered an embedded PDF. This task adds an actual
Chrome Stable browser smoke test to the existing disposable DevTools harness
as part of the existing Chrome CI viewer smoke step.

A loopback-only HTML document contains two different `iframe` PDF sources
and an ordinary HTML iframe control. The real browser must fetch both PDF
resources and the control, report two distinct child PDF frame URLs in its
frame tree, retain the parent HTML page, and expose a browser viewer/plugin
surface. An HTTP 200 or an iframe attribute alone does not pass the test.
An absent viewer or missing second frame fails CI; the test does not skip
because a browser could not display PDF content.

This checks embedded **same-origin HTTP PDF iframes in real Chrome on Linux**.
It does not claim Firefox, Safari, Edge, remote origins, opaque `blob:` or
`data:` frames behave identically. Browser-specific viewer verification
tasks are tracked separately; embedded behavior for those browsers remains
unverified until real-browser tests exist.

The fixture contains only generated, noninteractive PDF bytes and static HTML,
never user files. No network destinations other than local loopback are used.
Chrome runs in a disposable temporary profile, the extension remains inactive,
and no browser privileges or scanner integrations are activated. A rendered
PDF in the browser is **not evidence of native ClamAV scan-before-open**;
mandatory scanner gates, quarantine rules, and user preferences are untouched.

The regression test is auto-discovered by `npm test`. The existing Chrome viewer smoke step is a hard CI requirement and now
also tests iframes, alongside its top-level and authenticated PDF cases.
