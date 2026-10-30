# Browser capability flags (opener-0573)

The shared browser-capabilities.js module defines an immutable six-flag capability snapshot for Chromium, Firefox and Safari extension adapters. It does not identify browsers using user-agent strings, assume a browser supports an API, or request any permissions.

Call getBrowserCapabilityFlags(selectedNamespace) with the explicit runtime namespace chosen by integration code. The proposed browser-compatibility adapter (opener-0572) handles differences between browser and chrome namespaces independently; this module does not duplicate that work.

Three API-shape flags:
- runtimeMetadataApi: runtime.getManifest and runtime.getURL methods exist.
- runtimeMessagingApi: runtime.sendMessage and a complete runtime.onMessage listener interface exist.
- downloadEventsApi: downloads.onCreated, downloads.onChanged and downloads.onErased all have addListener and removeListener methods.

These three booleans are NOT evidence of effective permissions or authorization. Download events require separately verified browser permissions. A messaging interface is not an authenticated sender or authorization to open a PDF.

Three project-level integration gates remain explicitly false: nativeMessagingEnabled, pdfOpeningEnabled, and scannerVerificationEnabled. Even if a browser API exposes native messaging, this project has not configured a trusted native host, a PDF-opening route, or a scanner integration.

Incomplete, accessor-based, inherited, hostile, and missing API members fail closed. Detection calls no browser methods, registers no listeners, and returns a frozen snapshot rather than ongoing permission state.

Security boundary: Later code must independently verify user intent, browser permissions, message origin, ClamAV signatures and freshness, document integrity, quarantine status and the user-selected PDF application. These flags cannot establish that a PDF is harmless.

The existing npm test glob includes tests/browser-capabilities.test.mjs, executed by the existing required WebExtensions CI build-and-test step.
