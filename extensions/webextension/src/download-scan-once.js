import { subscribeToDownloadEvents } from "./download-monitoring.js";

// One browser download must not create multiple native scan requests. The
// extension remains inactive: only an explicitly opted-in trusted coordinator
// may construct this gate and supply its own scanner-request callback.
const MAX_RESERVED_DOWNLOADS = 256;

function own(value, name) {
  if (value === null || typeof value !== "object") return undefined;
  const descriptor = Object.getOwnPropertyDescriptor(value, name);
  return descriptor && Object.hasOwn(descriptor, "value") ? descriptor.value : undefined;
}

function verifiedPreflightId(value) {
  if (value === null || typeof value !== "object" || Array.isArray(value) ||
      ![Object.prototype, null].includes(Object.getPrototypeOf(value))) return null;
  const keys = Reflect.ownKeys(value);
  if (keys.length !== 5 || !["id", "transferComplete", "scanVerified",
    "authorizesScan", "authorizesOpen"].every((key) => keys.includes(key))) return null;
  const id = own(value, "id");
  if (!Number.isSafeInteger(id) || id < 0 ||
      own(value, "transferComplete") !== true ||
      own(value, "scanVerified") !== false ||
      own(value, "authorizesScan") !== false ||
      own(value, "authorizesOpen") !== false) return null;
  return id;
}

const outcomes = Object.freeze({
  unavailable: Object.freeze({ status: "unavailable", scanVerified: false, authorizesOpen: false }),
  duplicate: Object.freeze({ status: "duplicate", scanVerified: false, authorizesOpen: false }),
  capacity: Object.freeze({ status: "capacity-exhausted", scanVerified: false, authorizesOpen: false }),
  rejected: Object.freeze({ status: "submission-rejected", scanVerified: false, authorizesOpen: false }),
  submitted: Object.freeze({ status: "request-submitted", scanVerified: false, authorizesOpen: false })
});

/**
 * Reserve each completed download ID before invoking an async scan-submission
 * callback, including across callback failures, completion and reentrant calls.
 * Never evict an old ID to admit a new request: reaching the fixed cap fails
 * closed. Only a trusted onCreated/onErased lifecycle event permits ID reuse.
 *
 * A future trusted caller must first verify user consent, downloads permission
 * and a fresh completed-download preflight. A syntactically valid preflight is
 * not proof that the file is locally stable or authorized for scanning.
 * The callback receives NO browser metadata or arguments; native scan safety
 * and file identity checks remain independently mandatory.
 */
export function createCompletedDownloadScanRequestGate(downloadsApi) {
  const reserved = new Set();
  let active = true;
  const unsubscribe = subscribeToDownloadEvents(downloadsApi, (event) => {
    if (event.kind === "created" || event.kind === "erased") {
      reserved.delete(event.id);
    }
  });

  async function submitOnce(preflight, submitScanRequest) {
    let id;
    try {
      id = verifiedPreflightId(preflight);
    } catch {
      return outcomes.unavailable;
    }
    if (!active || id === null || typeof submitScanRequest !== "function") {
      return outcomes.unavailable;
    }
    if (reserved.has(id)) return outcomes.duplicate;
    if (reserved.size >= MAX_RESERVED_DOWNLOADS) return outcomes.capacity;

    // Reserve synchronously BEFORE calling user code or awaiting a Promise.
    // Rejections never unreserve, so a transient failure cannot cause a
    // duplicate request while the native host may still be processing it.
    reserved.add(id);
    try {
      const acknowledgment = await submitScanRequest();
      if (!active || own(acknowledgment, "accepted") !== true) return outcomes.rejected;
      // Accepted means only request submission, never clean scan or approval.
      return outcomes.submitted;
    } catch {
      // Do not log or expose source filenames or native error diagnostics.
      return outcomes.rejected;
    }
  }

  function dispose() {
    if (!active) return;
    active = false;
    unsubscribe();
    reserved.clear();
  }

  return Object.freeze({ submitOnce, dispose });
}
