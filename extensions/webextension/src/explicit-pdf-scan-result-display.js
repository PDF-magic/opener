// Passive presentation for a future authenticated Scan This PDF coordinator.
// Importing this module does not connect to native messaging or browser APIs.
export const EMPTY_EXPLICIT_SCAN_RESULT = "No verified scan result is available.";
const ID = /^[A-Za-z0-9_-]{1,80}$/u;
const LABELS = Object.freeze({
  clean: Object.freeze(["Scan complete: required checks found no threats. Opening still requires separate approval.", "status", "polite"]),
  malwareDetected: Object.freeze(["Malware detected. Opening is blocked. Keep this PDF closed.", "alert", "assertive"]),
  blocked: Object.freeze(["Scan did not establish a clean result. Do not open this PDF through PDF Magic Opener.", "alert", "assertive"])
});
const BLOCKED = new Set([
  "suspiciousStructure", "encrypted", "fileTooLarge", "fileChanged",
  "scanFailed", "incompleteScan", "scanTimedOut", "cancelled"
]);
const FAILED = new Set([
  "fileTooLarge", "fileChanged", "scanFailed", "incompleteScan",
  "scanTimedOut", "cancelled"
]);
const unavailable = Object.freeze({
  status: "unavailable", displayed: false, scanVerified: false, authorizesOpen: false
});

function own(record, key) {
  if (!record || typeof record !== "object") return undefined;
  const descriptor = Object.getOwnPropertyDescriptor(record, key);
  return descriptor && Object.hasOwn(descriptor, "value") ?
    descriptor.value : undefined;
}
function exact(record, fields) {
  if (!record || typeof record !== "object" || Array.isArray(record) ||
      ![Object.prototype, null].includes(Object.getPrototypeOf(record))) return false;
  const keys = Reflect.ownKeys(record);
  return keys.length === fields.length && fields.every(key =>
    keys.includes(key) && Object.hasOwn(Object.getOwnPropertyDescriptor(record, key), "value"));
}
function statusOf(message, requestId, scanRequestId) {
  if (!exact(message, ["version", "kind", "topic", "requestId", "payload"]) ||
      own(message, "version") !== 1 || own(message, "kind") !== "response" ||
      own(message, "topic") !== "scan.result" ||
      own(message, "requestId") !== requestId) return null;
  const payload = own(message, "payload");
  if (!exact(payload, ["scanRequestId", "status", "result",
    "scanCompleted", "scanVerified", "authorizesOpen"]) ||
      own(payload, "scanRequestId") !== scanRequestId ||
      own(payload, "authorizesOpen") !== false) return null;
  const result = own(payload, "result");
  if (!exact(result, ["status"])) return null;
  const status = own(result, "status");
  if (own(payload, "status") === "complete" &&
      own(payload, "scanCompleted") === true &&
      own(payload, "scanVerified") === true) {
    if (status === "clean" || status === "malwareDetected") return status;
    if (BLOCKED.has(status)) return "blocked";
  }
  if (own(payload, "status") === "failed" &&
      own(payload, "scanCompleted") === false &&
      own(payload, "scanVerified") === false &&
      FAILED.has(status)) return "blocked";
  return null;
}
function paint(target, status) {
  const label = LABELS[status];
  target.textContent = label ? label[0] : EMPTY_EXPLICIT_SCAN_RESULT;
  target.setAttribute("role", label ? label[1] : "status");
  target.setAttribute("aria-live", label ? label[2] : "polite");
}

/**
 * Display a separately authenticated, exactly correlated native scan result
 * in the trusted extension-owned popup paragraph. The coordinator must itself
 * verify the native scanner, selected PDF, complete scan and current request.
 * Its readiness flag or reported JSON fields are NOT authentication.
 */
export function createExplicitPdfScanResultDisplay(target, coordinator = null) {
  if (!target || target.nodeType !== 1 ||
      target.id !== "explicitPdfScanResult" ||
      typeof target.setAttribute !== "function" || !("textContent" in target)) {
    throw new TypeError("An extension-owned result element is required");
  }
  let disposed = false;
  let generation = 0;
  paint(target, null);

  function clear() {
    generation += 1;
    try { paint(target, null); } catch { /* never display stale success */ }
  }
  async function show({ requestId, scanRequestId, selectionId } = {}) {
    const ticket = ++generation;
    try {
      paint(target, null);
      if (disposed || ![requestId, scanRequestId, selectionId].every(
        value => typeof value === "string" && ID.test(value)
      ) || own(coordinator, "nativeScanResultsReady") !== true) return unavailable;
      const current = own(coordinator, "readCurrentSelectionId");
      const read = own(coordinator, "readVerifiedExplicitPdfScanResult");
      if (typeof current !== "function" || typeof read !== "function" ||
          current.call(coordinator) !== selectionId) return unavailable;
      const promise = read.call(coordinator, Object.freeze({
        requestId, scanRequestId, selectionId
      }));
      if (!promise || typeof promise.then !== "function") return unavailable;
      const message = await promise;
      if (disposed || ticket !== generation ||
          own(coordinator, "nativeScanResultsReady") !== true ||
          own(coordinator, "readCurrentSelectionId") !== current ||
          own(coordinator, "readVerifiedExplicitPdfScanResult") !== read ||
          current.call(coordinator) !== selectionId) return unavailable;
      const result = statusOf(message, requestId, scanRequestId);
      if (!result) return unavailable;
      paint(target, result);
      return Object.freeze({
        status: result, displayed: true,
        scanVerified: result === "clean" || result === "malwareDetected",
        authorizesOpen: false
      });
    } catch {
      if (ticket === generation) clear();
      return unavailable;
    }
  }
  function dispose() {
    if (disposed) return;
    disposed = true;
    clear();
  }
  return Object.freeze({ show, clear, dispose });
}
