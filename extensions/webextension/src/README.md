# Shared extension source

The shared Manifest V3 background module is `background.js` (opener-0568).
It is a deliberately inert entry point with no listeners, browser API calls,
network requests, PDF inspection or native messaging. It is copied to the
built extension root as `background.js`; the shared manifest references this
built file using `background.service_worker` and `type: "module"`.

Future browser handling, trust boundaries, permissions and PDF opening logic
require separate review. No content script or working integration exists.
