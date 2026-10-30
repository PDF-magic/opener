// This passive managed-workflow boundary MAY issue a trusted native open
// command only after obtaining a correlated completed/clean native scan report.
// It does not authenticate the coordinator, run ClamAV, or control browser UI.
const ID = /^[A-Za-z0-9_-]{1,80}$/u;
const MAX_IDS = 256;
const outcomes = Object.freeze({
  unavailable: Object.freeze({
    status: "unavailable", scanVerified: false, authorizesOpen: false, opened: false
  }),
  unverified: Object.freeze({
    status: "scan-not-verified", scanVerified: false, authorizesOpen: false, opened: false
  }),
  submitted: Object.freeze({
    status: "request-submitted", scanVerified: false, authorizesOpen: false, opened: false
  })
});

function own(value, key) {
  if (value === null || (typeof value !== "object" && typeof value !== "function")) {
    return undefined;
  }
  const descriptor = Object.getOwnPropertyDescriptor(value, key);
  return descriptor && Object.hasOwn(descriptor, "value") ? descriptor.value : undefined;
}

function exact(value, keys) {
  if (value === null || typeof value !== "object" || Array.isArray(value) ||
      ![Object.prototype, null].includes(Object.getPrototypeOf(value))) return false;
  const actual = Reflect.ownKeys(value);
  return actual.length === keys.length && keys.every(key => actual.includes(key)) &&
    keys.every(key => Object.hasOwn(Object.getOwnPropertyDescriptor(value, key), "value"));
}

function cleanCompletedNativeScan(response, id) {
  if (!exact(response, ["schemaVersion", "managedRequestId", "status",
    "scanCompleted", "scanVerified", "authorizesOpen", "result"]) ||
      own(response, "schemaVersion") !== 1 ||
      own(response, "managedRequestId") !== id ||
      own(response, "status") !== "complete" ||
      own(response, "scanCompleted") !== true ||
      own(response, "scanVerified") !== true ||
      // A scan report must not itself assert permission to launch a PDF.
      own(response, "authorizesOpen") !== false) return false;
  const result = own(response, "result");
  return exact(result, ["status"]) && own(result, "status") === "clean";
}

function correlatedAcknowledgement(value, id) {
  return exact(value, ["accepted", "managedRequestId"]) &&
    own(value, "accepted") === true && own(value, "managedRequestId") === id;
}

/**
 * Session-owned gate for a separately authenticated native managed workflow.
 *
 * The coordinator must control the scan evidence and own the consented
 * resource. Its readVerifiedManagedScanResult() MUST derive a complete clean
 * verdict from mandatory fresh ClamAV scanning and current canonical file
 * identity, never from browser-provided metadata. This JS layer cannot
 * authenticate an object or assert that a filesystem file has not changed.
 *
 * Even after a verified scan report, requestVerifiedManagedOpen() MUST
 * independently revalidate the whole native scan/integrity/quarantine/
 * selected-application policy immediately before any actual open. The
 * callback receives ONLY the immutable opaque request ID, no path or verdict.
 *
 * A request ID is reserved synchronously before any asynchronous work.
 * Rejected, incomplete, ambiguous or successful attempts remain reserved:
 * retrying an uncertain native request risks double opening. Native
 * idempotency after disconnect/restart is a separate requirement.
 *
 * This module never installs a listener, requests browser permissions,
 * opens a file, changes a setting or accesses a scanner on import.
 */
export function createManagedScanBeforeOpenGate(coordinator) {
  const reserved = new Set();
  let active = true;

  function available() {
    return own(coordinator, "nativeManagedWorkflowReady") === true &&
      own(coordinator, "nativeScanResultsReady") === true &&
      own(coordinator, "nativeVerifiedOpeningReady") === true &&
      typeof own(coordinator, "readVerifiedManagedScanResult") === "function" &&
      typeof own(coordinator, "requestVerifiedManagedOpen") === "function";
  }

  async function requestOpenIfScanned(managedRequestId) {
    try {
      if (!active || typeof managedRequestId !== "string" ||
          !ID.test(managedRequestId) || !available() ||
          reserved.has(managedRequestId) || reserved.size >= MAX_IDS) {
        return outcomes.unavailable;
      }
      reserved.add(managedRequestId); // One-shot across concurrent UI views.

      const read = own(coordinator, "readVerifiedManagedScanResult");
      const pending = read.call(coordinator, managedRequestId);
      if (!pending || typeof pending.then !== "function") return outcomes.unverified;
      const scan = await pending;
      if (!active || !available() ||
          !cleanCompletedNativeScan(scan, managedRequestId)) return outcomes.unverified;

      // The native open route must recheck live file identity, the effective
      // scanner verdict, quarantine and user's destination before launching.
      const open = own(coordinator, "requestVerifiedManagedOpen");
      const request = Object.freeze({ managedRequestId });
      const queued = open.call(coordinator, request);
      if (!queued || typeof queued.then !== "function") return outcomes.unavailable;
      const acknowledged = await queued;
      if (!active || !available() ||
          !correlatedAcknowledgement(acknowledged, managedRequestId)) {
        return outcomes.unavailable;
      }
      // Accepted is only an acknowledgement; do not claim the PDF opened.
      return outcomes.submitted;
    } catch {
      // Native failures can contain private paths, URLs and signatures.
      return outcomes.unavailable;
    }
  }

  function dispose() {
    active = false;
    reserved.clear();
  }

  return Object.freeze({ requestOpenIfScanned, dispose });
}
