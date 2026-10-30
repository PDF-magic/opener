# Native messaging caller-origin admission (opener-0653)

The standalone host checks browser launch arguments **before** reading a native
message. Chromium-family launches must carry an exact lowercase 32-character
`chrome-extension://` identity approved by an existing per-user host manifest.
Firefox passes a Gecko add-on identifier and the exact Firefox manifest path.
The manifest must identify `org.pdfmagic.opener`, use `stdio`, point to this
executable and include the exact approved origin or add-on ID. Invalid or
unregistered origins, symlinked manifests and unsafe paths fail closed.

An invocation with no browser arguments retains only the legacy transport
probe; it cannot scan or authorize opening. Launch arguments are **not
cryptographic proof** of browser identity, and a matching ID cannot establish
scanner trust, consent, file integrity or permission to open a PDF. All scan
and quarantine policy remains unchanged. The existing compiled-host test
suite includes positive and negative Chromium/Firefox cases.
