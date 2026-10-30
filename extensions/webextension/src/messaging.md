# Shared extension messaging (opener-0569)

`messaging.js` defines a **transport-independent JSON message envelope** for
future Chromium, Firefox and Safari WebExtensions code. It neither registers
browser listeners nor sends messages, accesses files, launches a PDF, contacts
native messaging hosts, or requests permissions. Nothing imports this module
from a runtime entry point yet; packaging and routing are separate tasks.

The module exports `MESSAGE_VERSION` (currently `1`), `MAX_MESSAGE_BYTES`
(16 KiB), `createMessage`, `parseMessage`, and `serializeMessage`.

```js
import { createMessage, parseMessage, serializeMessage } from "./messaging.js";

const outgoing = createMessage("request", "example.ping", "request_1", { count: 1 });
const json = serializeMessage(outgoing);
const incoming = parseMessage(json); // Also accepts a browser-delivered object.
```

The envelope has exactly `version`, `kind`, `topic`, `requestId` and
`payload`. Allowed kinds are `request`, `response` and `event`.
Topics and request IDs are bounded ASCII identifiers; payloads must be plain,
acyclic JSON values with bounded depth, size and count. Unknown protocol
versions, fields, executable/accessor values and unsafe object keys fail
closed with path-free errors. Returned messages are detached copies. No
message types or topics are registered to trigger actions in this task.

**Security boundary:** Validation is not authentication, sender/origin
verification, authorization, malware scanning, or an opening verdict. A
future transport must independently authenticate its sender, validate
message-specific payloads, preserve ClamAV/freshness/integrity/quarantine
requirements and the user's selected destination application, and never
treat a message as proof that a PDF is harmless.

Tests: `npm test` from `extensions/webextension/` automatically includes
`tests/messaging.test.mjs` through the existing `tests/*.test.mjs` glob.
The established WebExtensions build-and-test step in GitHub CI runs it.
