import { describeExplicitPdfScanRequest } from "./explicit-pdf-scan-request.js";

// Fail-closed, opt-in cleanup of a private temporary PDF lease.
// User-selected browser downloads, originals and quarantine are never deleted.
const ID = /^[A-Za-z0-9_-]{1,80}$/u;
const MAX_ATTEMPTS = 128;
const FIELDS = Object.freeze([
  "requestId", "selectionId", "downloadId", "leaseId", "scope", "policy",
  "state", "appOwned", "identityVerified", "scanActive", "openActive",
  "quarantineHold", "userOwned", "verified"
]);
const unavailable = Object.freeze({
  status: "unavailable", removed: false, scanVerified: false, authorizesOpen: false
});
const deferred = Object.freeze({
  status: "deferred", removed: false, scanVerified: false, authorizesOpen: false
});
const retained = Object.freeze({
  status: "retained", removed: false, scanVerified: false, authorizesOpen: false
});
const removed = Object.freeze({
  status: "removed", removed: true, scanVerified: false, authorizesOpen: false
});

function own(value, key) {
  if (value === null || (typeof value !== "object" && typeof value !== "function")) {
    return undefined;
  }
  const property = Object.getOwnPropertyDescriptor(value, key);
  return property && Object.hasOwn(property, "value") ? property.value : undefined;
}

function exact(value, fields) {
  if (value === null || typeof value !== "object" || Array.isArray(value) ||
      ![Object.prototype, null].includes(Object.getPrototypeOf(value))) return false;
  const keys = Reflect.ownKeys(value);
  return keys.length === fields.length && keys.every(key =>
    typeof key === "string" && fields.includes(key) &&
    Object.hasOwn(Object.getOwnPropertyDescriptor(value, key), "value"));
}

function validLease(snapshot, reference) {
  if (!exact(snapshot, FIELDS) ||
      own(snapshot, "requestId") !== reference.requestId ||
      own(snapshot, "selectionId") !== reference.selectionId ||
      own(snapshot, "downloadId") !== reference.downloadId ||
      own(snapshot, "leaseId") !== reference.leaseId ||
      own(snapshot, "verified") !== true ||
      own(snapshot, "identityVerified") !== true ||
      !["delete-after-use", "retain"].includes(own(snapshot, "policy")) ||
      !["active", "retired"].includes(own(snapshot, "state"))) return false;

  const scope = own(snapshot, "scope");
  const temporary = scope === "explicit-pdf-temporary";
  if (!temporary && scope !== "user-selected-download" &&
      scope !== "existing-local-pdf") return false;
  if (temporary) {
    return own(snapshot, "appOwned") === true &&
      own(snapshot, "userOwned") === false;
  }
  // A saved or previously existing file can only have the retain policy.
  return own(snapshot, "appOwned") === false &&
    own(snapshot, "userOwned") === true &&
    own(snapshot, "policy") === "retain";
}

function decision(snapshot) {
  if (own(snapshot, "scope") !== "explicit-pdf-temporary" ||
      own(snapshot, "policy") === "retain") return retained;
  // Native leases remain allocated while scanner, opening or quarantine holds
  // them. A retired lease means no later Open Scanned PDF action needs it.
  if (own(snapshot, "state") !== "retired" ||
      own(snapshot, "scanActive") !== false ||
      own(snapshot, "openActive") !== false ||
      own(snapshot, "quarantineHold") !== false) return deferred;
  return null;
}

/**
 * A native-owned deletion operation for a separately authenticated explicit
 * PDF session. A coordinator must independently attest the exact lease,
 * app-private ownership, unchanged file identity, active users, and policy.
 * It must securely unlink ONLY its own lease (never a supplied path), without
 * following symlinks or deleting browser-managed user downloads.
 *
 * No browser downloads.erase/removeFile, filesystem API, or native listener
 * is registered here. Native acknowledgement is not sufficient: a separate
 * trusted post-delete check must confirm that the lease is gone.
 */
export function createExplicitPdfTemporaryCleanup(coordinator = null) {
  const attempted = new Set();
  let disposed = false;
  let generation = 0;

  async function cleanup({ request, downloadId, leaseId } = {}) {
    try {
      if (disposed) return unavailable;
      const intent = describeExplicitPdfScanRequest(request);
      if (!intent || !Number.isSafeInteger(downloadId) || downloadId < 0 ||
          typeof leaseId !== "string" || !ID.test(leaseId) ||
          own(coordinator, "nativeTemporaryCleanupReady") !== true) return unavailable;

      const current = own(coordinator, "readCurrentSelectionId");
      const read = own(coordinator, "readVerifiedTemporaryPdfLease");
      const erase = own(coordinator, "removeVerifiedTemporaryPdfLease");
      const confirm = own(coordinator, "verifyTemporaryPdfLeaseRemoved");
      if (typeof current !== "function" || typeof read !== "function" ||
          typeof erase !== "function" || typeof confirm !== "function" ||
          current.call(coordinator) !== intent.selectionId) return unavailable;

      const reference = Object.freeze({
        requestId: intent.requestId, selectionId: intent.selectionId,
        downloadId, leaseId
      });
      const key = intent.requestId + ":" + leaseId;
      if (attempted.has(key) || attempted.size >= MAX_ATTEMPTS) return unavailable;
      const snapshot = read.call(coordinator, reference);
      if (!validLease(snapshot, reference)) return unavailable;
      const choice = decision(snapshot);
      if (choice) return choice;

      // Recheck immediately before deletion; no unrelated identifier, user
      // download, active scanner/open or quarantined file can be removed.
      if (own(coordinator, "nativeTemporaryCleanupReady") !== true ||
          own(coordinator, "readVerifiedTemporaryPdfLease") !== read ||
          own(coordinator, "removeVerifiedTemporaryPdfLease") !== erase ||
          own(coordinator, "verifyTemporaryPdfLeaseRemoved") !== confirm ||
          own(coordinator, "readCurrentSelectionId") !== current ||
          current.call(coordinator) !== intent.selectionId) return unavailable;
      const again = read.call(coordinator, reference);
      if (!validLease(again, reference) || decision(again) !== null) return deferred;

      attempted.add(key); // Never retry uncertain native deletion.
      const version = generation;
      const operation = erase.call(coordinator, reference);
      if (!operation || typeof operation.then !== "function") return unavailable;
      const ack = await operation;
      if (disposed || version !== generation ||
          own(coordinator, "nativeTemporaryCleanupReady") !== true ||
          !exact(ack, ["leaseId", "removed"]) ||
          own(ack, "leaseId") !== leaseId || own(ack, "removed") !== true) {
        return unavailable;
      }
      const inspection = confirm.call(coordinator, reference);
      if (!inspection || typeof inspection.then !== "function") return unavailable;
      const proof = await inspection;
      if (disposed || version !== generation ||
          own(coordinator, "nativeTemporaryCleanupReady") !== true ||
          !exact(proof, ["leaseId", "absent"]) ||
          own(proof, "leaseId") !== leaseId || own(proof, "absent") !== true) {
        return unavailable;
      }
      return removed;
    } catch {
      // Local filesystem failures, paths and signed URLs must stay private.
      return unavailable;
    }
  }

  function dispose() {
    disposed = true;
    generation += 1;
    attempted.clear();
  }

  return Object.freeze({ cleanup, dispose });
}
