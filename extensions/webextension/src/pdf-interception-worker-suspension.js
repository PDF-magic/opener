import { getPdfInterceptionPointAssessment } from "./pdf-interception-point-assessment.js";

// Passive worker-lifetime fence for an independently trusted interception
// coordinator. Importing this module never subscribes to runtime.onSuspend,
// connects a native host, changes a browser setting or opens PDF bytes.
export const PDF_WORKER_SUSPENSION_VERSION = 1;
const MAX_ACTIVATIONS = 64;
const MAX_TICKETS = 128;
const ID = /^[A-Za-z0-9_-]{1,80}$/u;
const WAKE_KEYS = ["version", "kind", "browserId", "activationId"];
const PROOF_KEYS = ["kind", "browserId", "activationId", "verified"];
const CLEANUP_KEYS = ["kind", "browserId", "activationId", "orphanedScansCancelled"];
const UNAVAILABLE = Object.freeze({
  status: "unavailable", workerReconciled: false,
  scanVerified: false, automaticInterceptionEnabled: false,
  authorizesScan: false, authorizesOpen: false
});

function own(value, key) {
  if (!value || (typeof value !== "object" && typeof value !== "function")) {
    return undefined;
  }
  const descriptor = Object.getOwnPropertyDescriptor(value, key);
  return descriptor && Object.hasOwn(descriptor, "value") ?
    descriptor.value : undefined;
}

function exact(value, keys) {
  if (!value || typeof value !== "object" || Array.isArray(value) ||
      ![Object.prototype, null].includes(Object.getPrototypeOf(value))) return false;
  const actual = Reflect.ownKeys(value);
  return actual.length === keys.length &&
    keys.every(key => actual.includes(key) &&
      Object.hasOwn(Object.getOwnPropertyDescriptor(value, key), "value"));
}

function outcome(status, workerReconciled) {
  return Object.freeze({
    status, workerReconciled, scanVerified: false,
    automaticInterceptionEnabled: false, authorizesScan: false,
    authorizesOpen: false
  });
}

/**
 * A worker's in-memory promises and held-response callbacks cannot survive
 * suspension as trusted scan evidence. Each *real* worker activation must
 * independently revoke old browser response holds and reconcile abandoned
 * native scans before issuing fresh lifetime tickets.
 *
 * A production native coordinator must enforce its own durable, bounded hold
 * lease and cancel/quarantine orphaned work even if runtime.onSuspend never
 * fires; neither this in-memory guard nor a service-worker timer can do so.
 * Injected callbacks are NOT credentials: the integrating code must verify
 * browser/profile provenance and make held response revocation synchronous.
 */
export function createPdfInterceptionWorkerSuspensionGuard(coordinator) {
  const tickets = new Set();
  const activations = new Set();
  let generation = 0;
  let status = "wake-required";
  let verifying = false;
  let owner = null;

  function invalidate(nextStatus) {
    generation++;
    tickets.clear();
    status = nextStatus;
  }

  function cancelBestEffort(ownerSnapshot) {
    try {
      const revoke = own(coordinator, "revokePreviousWorkerHolds");
      if (typeof revoke === "function") {
        // Not awaited: an onSuspend callback cannot rely on async completion.
        Promise.resolve(revoke.call(coordinator, ownerSnapshot)).catch(() => {});
      }
    } catch { /* native durable lease must fail closed independently */ }
    try {
      const cancel = own(coordinator, "cancelOrphanedWorkerScans");
      if (typeof cancel === "function") {
        Promise.resolve(cancel.call(coordinator, ownerSnapshot)).catch(() => {});
      }
    } catch { /* late cleanup cannot re-enable this worker */ }
  }

  /**
   * Optional synchronous notification. MV3 may never deliver this event.
   * First revoke every ticket, then attempt best-effort native cleanup.
   * No async work is required for the session to become unusable.
   */
  function suspend() {
    if (status === "disposed" || status === "suspended") return;
    invalidate("suspended");
    if (owner !== null) cancelBestEffort(owner);
  }

  /**
   * Call on every independently verified worker activation, including
   * silent termination and subsequent wake in the same browser session.
   * A cold-browser startup is a separate event owned by opener-0793.
   */
  async function reconcileWake(wake) {
    if (status === "disposed" || verifying) return UNAVAILABLE;
    let verify, revoke, cancel, snapshot;
    try {
      if (!exact(wake, WAKE_KEYS) ||
          own(wake, "version") !== PDF_WORKER_SUSPENSION_VERSION ||
          own(wake, "kind") !== "service-worker-activation" ||
          typeof own(wake, "browserId") !== "string" ||
          getPdfInterceptionPointAssessment(own(wake, "browserId")).browserId === null ||
          typeof own(wake, "activationId") !== "string" ||
          !ID.test(own(wake, "activationId")) ||
          activations.size >= MAX_ACTIVATIONS ||
          activations.has(own(wake, "activationId"))) return UNAVAILABLE;

      verify = own(coordinator, "verifyWorkerActivation");
      revoke = own(coordinator, "revokePreviousWorkerHolds");
      cancel = own(coordinator, "cancelOrphanedWorkerScans");
      if ([verify, revoke, cancel].some(fn => typeof fn !== "function")) {
        return UNAVAILABLE;
      }
      verifying = true;
      try {
        snapshot = Object.freeze({
          browserId: own(wake, "browserId"), activationId: own(wake, "activationId")
        });
        // Must be a synchronous, independently verified activation proof.
        const beforeProof = generation;
        const proof = verify.call(coordinator, snapshot);
        if (generation !== beforeProof || status === "disposed") return UNAVAILABLE;
        if (!exact(proof, PROOF_KEYS) ||
            own(proof, "kind") !== "verified-service-worker-activation" ||
            own(proof, "verified") !== true ||
            own(proof, "browserId") !== snapshot.browserId ||
            own(proof, "activationId") !== snapshot.activationId) return UNAVAILABLE;
        activations.add(snapshot.activationId);
        // Invalidate *before* invoking any native/browser callbacks. A late
        // result or callback re-entry cannot use the prior worker's ticket.
        invalidate("reconciling");
        owner = snapshot;
      } finally {
        verifying = false;
      }
    } catch {
      return UNAVAILABLE;
    }

    const epoch = generation;
    let revoked = false;
    try {
      revoked = revoke.call(coordinator, snapshot) === true;
    } catch { /* still request orphan cancellation */ }
    let cancelled = false;
    try {
      const pending = cancel.call(coordinator, snapshot);
      if (pending && typeof pending.then === "function") {
        const receipt = await pending;
        cancelled = exact(receipt, CLEANUP_KEYS) &&
          own(receipt, "kind") === "native-worker-orphans-cancelled" &&
          own(receipt, "browserId") === snapshot.browserId &&
          own(receipt, "activationId") === snapshot.activationId &&
          own(receipt, "orphanedScansCancelled") === true;
      }
    } catch { /* no confirmed cancellation => no new work */ }

    if (generation !== epoch || status === "disposed") return UNAVAILABLE;
    try {
      if (!revoked || !cancelled ||
          own(coordinator, "verifyWorkerActivation") !== verify ||
          own(coordinator, "revokePreviousWorkerHolds") !== revoke ||
          own(coordinator, "cancelOrphanedWorkerScans") !== cancel) {
        invalidate("unavailable");
        return UNAVAILABLE;
      }
    } catch {
      invalidate("unavailable");
      return UNAVAILABLE;
    }
    status = "reconciled";
    return outcome("orphan-cleanup-confirmed", true);
  }

  function issueTicket() {
    if (status !== "reconciled" || tickets.size >= MAX_TICKETS) return null;
    const ticket = Symbol("worker-lifetime-only");
    tickets.add(ticket);
    return ticket;
  }

  function isCurrent(ticket) {
    // Local lifetime only: NEVER sufficient to open or release a PDF. A
    // native-held response must independently check its durable lease and a
    // fresh clean-scanner verdict at the instant of release.
    return status === "reconciled" && tickets.has(ticket);
  }

  function release(ticket) {
    // Release drops a local lifetime token; it does not release PDF bytes.
    return status === "reconciled" && tickets.delete(ticket);
  }

  function dispose() {
    if (status === "disposed") return;
    const previous = owner;
    invalidate("disposed");
    if (previous !== null) cancelBestEffort(previous);
  }

  return Object.freeze({
    reconcileWake, suspend, issueTicket, isCurrent, release, dispose,
    get status() { return status; }
  });
}
