// Passive, privacy-safe scanner-unavailable alert for completed PDF downloads.
// The inactive background and popup never subscribe to native messages here.
// A trusted extension integration supplies verified host/lifecycle responses.
const ID = /^[A-Za-z0-9_-]{1,80}$/u;
const HOST_CODES = new Set([
  "native-host-unavailable", "native-permission-denied",
  "native-connection-disconnected", "native-handshake-failed",
  "native-connection-timeout", "native-connection-failed"
]);
const UNAVAILABLE = Object.freeze({
  status: "unavailable", scannerUnavailable: false,
  scanVerified: false, authorizesOpen: false
});
const DISPLAYED = Object.freeze({
  status: "displayed", scannerUnavailable: true,
  scanVerified: false, authorizesOpen: false
});
const TITLE = "Scanner unavailable — PDF not scanned";
const DETAIL =
  "The required native scanner is unavailable. This PDF was not verified and must not be opened through PDF Magic Opener.";

function own(object, key) {
  const descriptor = Object.getOwnPropertyDescriptor(object, key);
  return descriptor && Object.hasOwn(descriptor, "value") ? descriptor.value : undefined;
}

function exact(value, fields) {
  if (!value || typeof value !== "object" || Array.isArray(value) ||
      ![Object.prototype, null].includes(Object.getPrototypeOf(value))) return false;
  const keys = Reflect.ownKeys(value);
  return keys.length === fields.length &&
    fields.every(key => keys.includes(key) &&
      Object.hasOwn(Object.getOwnPropertyDescriptor(value, key), "value"));
}

function transportUnavailable(payload) {
  return own(payload, "status") === "unavailable" &&
    own(payload, "reason") === "trusted-scan-coordinator-required" &&
    own(payload, "scanAvailable") === false &&
    own(payload, "scanStarted") === false &&
    own(payload, "scanVerified") === false &&
    own(payload, "authorizesOpen") === false;
}

function isUnavailableResponse(message, expectedRequestId, expectedScanRequestId) {
  try {
    if (typeof expectedRequestId !== "string" || !ID.test(expectedRequestId) ||
        !exact(message, ["version", "kind", "topic", "requestId", "payload"]) ||
        own(message, "version") !== 1 ||
        own(message, "kind") !== "response" ||
        own(message, "requestId") !== expectedRequestId) return false;
    const topic = own(message, "topic");
    const payload = own(message, "payload");

    if (topic === "scan.request") {
      return exact(payload, ["status", "reason", "scanAvailable",
        "scanStarted", "scanVerified", "authorizesOpen"]) &&
        transportUnavailable(payload);
    }
    if (topic === "scan.status") {
      return typeof expectedScanRequestId === "string" &&
        ID.test(expectedScanRequestId) &&
        exact(payload, ["scanRequestId", "status", "reason", "scanAvailable",
          "scanStarted", "scanVerified", "authorizesOpen"]) &&
        own(payload, "scanRequestId") === expectedScanRequestId &&
        transportUnavailable(payload);
    }
    if (topic === "scan.result") {
      return typeof expectedScanRequestId === "string" &&
        ID.test(expectedScanRequestId) &&
        exact(payload, ["scanRequestId", "status", "reason", "result",
          "scanCompleted", "scanVerified", "authorizesOpen"]) &&
        own(payload, "scanRequestId") === expectedScanRequestId &&
        own(payload, "status") === "unavailable" &&
        own(payload, "reason") === "trusted-scan-coordinator-required" &&
        own(payload, "result") === null &&
        own(payload, "scanCompleted") === false &&
        own(payload, "scanVerified") === false &&
        own(payload, "authorizesOpen") === false;
    }
    if (topic === "host.connection") {
      return exact(payload, ["status", "code", "connected", "scanAvailable",
        "scanStarted", "scanVerified", "authorizesOpen"]) &&
        own(payload, "status") === "error" &&
        HOST_CODES.has(own(payload, "code")) &&
        own(payload, "connected") === false &&
        own(payload, "scanAvailable") === false &&
        own(payload, "scanStarted") === false &&
        own(payload, "scanVerified") === false &&
        own(payload, "authorizesOpen") === false;
    }
    return false;
  } catch {
    // Proxies and accessors never manufacture scanner-unavailable evidence.
    return false;
  }
}

function validRoot(root) {
  try {
    return root?.nodeType === 1 &&
      typeof root.ownerDocument?.createElement === "function" &&
      typeof root.replaceChildren === "function" &&
      typeof root.setAttribute === "function" &&
      typeof root.removeAttribute === "function";
  } catch {
    return false;
  }
}

/**
 * Render fixed scanner-unavailable text into an extension-owned UI element.
 * Caller MUST authenticate native responses or independently establish a
 * local native-scanner-absent condition; this helper is not authentication.
 * Neither a transport failure nor this warning authorizes opening a PDF.
 * Importing does not activate native communication or browser listeners.
 */
export function createDownloadScannerUnavailableDisplay(root) {
  if (!validRoot(root)) {
    throw new TypeError("An extension-owned status element is required");
  }
  let active = true;

  function clear() {
    root.replaceChildren();
    root.hidden = true;
    root.removeAttribute("role");
    root.removeAttribute("aria-live");
  }

  function render() {
    if (!active) return UNAVAILABLE;
    const heading = root.ownerDocument.createElement("strong");
    heading.textContent = TITLE;
    const detail = root.ownerDocument.createElement("p");
    detail.textContent = DETAIL;
    root.replaceChildren(heading, detail);
    root.setAttribute("role", "alert");
    root.setAttribute("aria-live", "assertive");
    root.hidden = false;
    return DISPLAYED;
  }

  // Display an explicit absence detected by trusted local connection logic;
  // no fabricated native response or scan-result claim is involved.
  function showLocalUnavailable() {
    try { return render(); } catch {
      try { clear(); } catch { /* fail closed */ }
      return UNAVAILABLE;
    }
  }

  function show(message, expected = {}) {
    let valid = false;
    try {
      valid = active && isUnavailableResponse(
        message, own(expected, "requestId"), own(expected, "scanRequestId")
      );
    } catch { /* malformed expectations cannot trigger a warning */ }
    try {
      clear(); // A later or unrelated response must remove any stale alert.
      return valid ? render() : UNAVAILABLE;
    } catch {
      return UNAVAILABLE;
    }
  }

  function dispose() {
    if (!active) return;
    active = false;
    try { clear(); } catch { /* fail closed */ }
  }

  clear();
  return Object.freeze({ show, showLocalUnavailable, clear, dispose });
}
