// Passive, fail-closed recovery contract for a newly initialized extension
// execution context. The shipped background stays inert. No API listeners,
// browser navigation, persistence, native scanner or PDF release is installed.
export const EXTENSION_RESTART_PROTOCOL_VERSION = 1;
export const EXTENSION_RESTART_REASONS = Object.freeze([
  "worker-reinitialized", "extension-reloaded", "extension-updated"
]);

const ID = /^[A-Za-z0-9_-]{1,80}$/u;
const MAX_EPOCHS = 64;
const MAX_TICKETS = 128;
const CONTEXT_FIELDS = Object.freeze(["version", "kind", "epochId", "reason"]);
const VERIFIED_FIELDS = Object.freeze(["kind", "epochId", "reason", "verified"]);
const CLEANED_FIELDS = Object.freeze(["kind", "epochId", "orphanedScansCancelled"]);
const blocked = Object.freeze({
  status: "unavailable", oldContextInvalidated: false,
  nativeOrphansCancelled: false, scanVerified: false,
  automaticInterceptionEnabled: false, authorizesOpen: false
});
function outcome(status, invalidated, cancelled = false) {
  return Object.freeze({
    status, oldContextInvalidated: invalidated,
    nativeOrphansCancelled: cancelled, scanVerified: false,
    automaticInterceptionEnabled: false, authorizesOpen: false
  });
}
function own(value, key) {
  if (value === null || (typeof value !== "object" &&
      typeof value !== "function")) return undefined;
  try {
    const descriptor = Object.getOwnPropertyDescriptor(value, key);
    return descriptor && Object.hasOwn(descriptor, "value") ?
      descriptor.value : undefined;
  } catch {
    return undefined;
  }
}
function exact(value, fields) {
  if (value === null || typeof value !== "object" || Array.isArray(value) ||
      ![Object.prototype, null].includes(Object.getPrototypeOf(value))) return false;
  const keys = Reflect.ownKeys(value);
  return keys.length === fields.length &&
    keys.every(key => typeof key === "string" && fields.includes(key) &&
      Object.hasOwn(Object.getOwnPropertyDescriptor(value, key), "value"));
}

/**
 * Fail closed when a new extension execution context replaces a prior worker,
 * is reloaded, or is updated. This MUST be explicitly invoked by a trusted
 * extension/native coordinator after genuine extension context initialization,
 * not by page scripts, popup messages or an untrusted runtime event argument.
 * A Chrome/Firefox MV3 worker wake is not necessarily a whole browser restart.
 *
 * The coordinator must independently authenticate its context/epoch and own a
 * durable native ledger of abandoned interception jobs. The injected hooks:
 *   verifyExtensionContextEpoch({epochId, reason}) -> synchronous proof;
 *   quarantinePreviousExtensionHolds({epochId, reason}) -> true synchronously;
 *   cancelOrphanedExtensionScans({epochId, reason}) -> Promise<exact result>.
 * Quarantine must make any previous holding page non-resumable, without
 * reloading/replaying its URL. Native cleanup must cancel/quarantine stale
 * jobs; it MUST NOT reconnect a previous clean verdict or re-open a PDF.
 *
 * This guard never permits an old scan to resume; successful reconciliation
 * only issues in-memory lifetime tickets for independently authorized NEW
 * sessions. Crash, lost Port, interrupted cleanup and stale results block.
 */
export function createPdfInterceptionExtensionRestartGuard(coordinator = null) {
  const seen = new Set();
  const tickets = new Set();
  let generation = 0;
  let state = "context-required";
  let verifying = false;
  let methods = null;
  let lastContext = null;

  function stillTrusted() {
    return state === "reconciled" && methods !== null &&
      own(coordinator, "verifyExtensionContextEpoch") === methods.verify &&
      own(coordinator, "quarantinePreviousExtensionHolds") === methods.quarantine &&
      own(coordinator, "cancelOrphanedExtensionScans") === methods.cancel;
  }
  function issueTicket() {
    if (!stillTrusted() || tickets.size >= MAX_TICKETS) return null;
    const ticket = Symbol("extension-context-lifetime");
    tickets.add(ticket);
    return ticket;
  }
  function isCurrent(ticket) {
    return stillTrusted() && tickets.has(ticket);
  }
  function release(ticket) {
    return stillTrusted() && tickets.delete(ticket);
  }
  async function reconcile(context) {
    if (state === "disposed" || verifying) return blocked;
    let verify, quarantine, cancel, reference;
    try {
      if (!exact(context, CONTEXT_FIELDS) ||
          own(context, "version") !== EXTENSION_RESTART_PROTOCOL_VERSION ||
          own(context, "kind") !== "extension-context-initialized" ||
          !ID.test(own(context, "epochId")) ||
          !EXTENSION_RESTART_REASONS.includes(own(context, "reason")) ||
          seen.has(own(context, "epochId")) || seen.size >= MAX_EPOCHS) {
        return blocked;
      }
      verify = own(coordinator, "verifyExtensionContextEpoch");
      quarantine = own(coordinator, "quarantinePreviousExtensionHolds");
      cancel = own(coordinator, "cancelOrphanedExtensionScans");
      if ([verify, quarantine, cancel].some(fn => typeof fn !== "function")) {
        return blocked;
      }
      reference = Object.freeze({
        epochId: own(context, "epochId"), reason: own(context, "reason")
      });

      // A new validly shaped context invalidates all old in-memory tickets
      // synchronously, before invoking even the synchronous proof callback.
      generation++;
      tickets.clear();
      methods = null;
      state = "reconciling";
      seen.add(reference.epochId);
      lastContext = reference;
      verifying = true;
      let proof;
      const verificationEpoch = generation;
      try {
        proof = verify.call(coordinator, reference);
      } finally {
        verifying = false;
      }
      if (state !== "reconciling" || generation !== verificationEpoch) {
        return outcome("unavailable", true);
      }
      // Reject asynchronous proof immediately; consume its rejection rather
      // than ever treating a later resolution as extension authentication.
      if (proof && typeof proof.then === "function") {
        Promise.resolve(proof).catch(() => {});
        state = "unavailable";
        return outcome("unavailable", true);
      }
      if (!exact(proof, VERIFIED_FIELDS) ||
          own(proof, "kind") !== "verified-extension-context" ||
          own(proof, "epochId") !== reference.epochId ||
          own(proof, "reason") !== reference.reason ||
          own(proof, "verified") !== true) {
        state = "unavailable";
        return outcome("unavailable", true);
      }
    } catch {
      verifying = false;
      if (state === "reconciling") state = "unavailable";
      return outcome("unavailable", state !== "context-required");
    }

    const epoch = generation;
    let quarantined = false;
    try {
      // This first safety barrier MUST be synchronous. A Promise is failure.
      quarantined = quarantine.call(coordinator, reference) === true;
    } catch { /* Still attempt native orphan cleanup. */ }

    let cancelled = false;
    try {
      const pending = cancel.call(coordinator, reference);
      if (pending && typeof pending.then === "function") {
        const result = await pending;
        cancelled = exact(result, CLEANED_FIELDS) &&
          own(result, "kind") === "extension-native-orphans-cancelled" &&
          own(result, "epochId") === reference.epochId &&
          own(result, "orphanedScansCancelled") === true;
      }
    } catch { /* Unknown native outcome remains blocked. */ }

    if (state === "disposed" || generation !== epoch) {
      return outcome("unavailable", true);
    }
    if (!quarantined || !cancelled ||
        own(coordinator, "verifyExtensionContextEpoch") !== verify ||
        own(coordinator, "quarantinePreviousExtensionHolds") !== quarantine ||
        own(coordinator, "cancelOrphanedExtensionScans") !== cancel) {
      state = "unavailable";
      return outcome("unavailable", true);
    }
    methods = { verify, quarantine, cancel };
    state = "reconciled";
    return outcome("orphan-cleanup-confirmed", true, true);
  }

  function dispose() {
    if (state === "disposed") return;
    generation++;
    tickets.clear();
    methods = null;
    state = "disposed";
    if (lastContext) {
      try {
        const quarantine = own(coordinator, "quarantinePreviousExtensionHolds");
        if (typeof quarantine === "function") {
          Promise.resolve(quarantine.call(coordinator, lastContext)).catch(() => {});
        }
      } catch { /* Invalidation is irrevocable despite cleanup failure. */ }
    }
  }

  return Object.freeze({
    reconcile, issueTicket, isCurrent, release, dispose,
    get status() { return state; }
  });
}
