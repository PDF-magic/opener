import { getPdfInterceptionPointAssessment } from "./pdf-interception-point-assessment.js";

// Passive browser-restart reconciliation. Only an independently authenticated
// native/browser coordinator can implement the two injected cleanup callbacks.
// This does not install a browser listener, restart scans or release PDF bytes.
export const PDF_INTERCEPTION_RESTART_VERSION = 1;
const MAX_STARTUPS = 64;
const MAX_TICKETS = 128;
const ID = /^[A-Za-z0-9_-]{1,80}$/u;
const STARTUP_FIELDS = Object.freeze(["version", "kind", "browserId", "startupId"]);
const PROOF_FIELDS = Object.freeze([
  "kind", "browserId", "startupId", "verified"
]);
const CLEANUP_FIELDS = Object.freeze([
  "kind", "browserId", "startupId", "orphanedScansCancelled"
]);

function own(value, key) {
  if (value === null || (typeof value !== "object" &&
      typeof value !== "function")) return undefined;
  const descriptor = Object.getOwnPropertyDescriptor(value, key);
  return descriptor && Object.hasOwn(descriptor, "value") ?
    descriptor.value : undefined;
}

function exactRecord(value, expected) {
  if (value === null || typeof value !== "object" || Array.isArray(value) ||
      ![Object.prototype, null].includes(Object.getPrototypeOf(value))) return false;
  const keys = Reflect.ownKeys(value);
  return keys.length === expected.length &&
    keys.every(key => typeof key === "string" && expected.includes(key) &&
      Object.hasOwn(Object.getOwnPropertyDescriptor(value, key), "value"));
}

const BLOCKED = Object.freeze({
  status: "unavailable", oldSessionsInvalidated: false,
  nativeOrphansCancelled: false, scanVerified: false,
  automaticInterceptionEnabled: false, authorizesOpen: false
});
function result(status, invalidated, cancelled = false) {
  return Object.freeze({
    status, oldSessionsInvalidated: invalidated,
    nativeOrphansCancelled: cancelled, scanVerified: false,
    automaticInterceptionEnabled: false, authorizesOpen: false
  });
}

/**
 * A future trusted browser/native integration invokes reconcileStartup only
 * on a verified *cold browser startup* (not on every MV3 worker wake).
 *
 * Every accepted new startup synchronously expires all previous lifetime
 * tickets BEFORE invoking coordinator-owned cleanup; it requests native
 * cancellation of orphaned interception scans even when the new process has
 * no in-memory knowledge of the previous process. A successful cleanup reply
 * only allows new lifetime tickets; it never authorizes scanning or opening.
 *
 * The native coordinator must keep its own durable per-installation ledger of
 * in-flight interceptions and cancel/quarantine it, scoped to this browser.
 * The injected verification and cleanup methods, including their responses,
 * are not security credentials; their provenance MUST be established outside
 * this JavaScript module. No stale localStorage/sessionStorage/page message
 * or browser-restored tab may reconstitute a previously trusted scan.
 */
export function createPdfInterceptionBrowserRestartGuard(coordinator) {
  const seenStartups = new Set();
  const tickets = new Set();
  let generation = 0;
  let state = "startup-required";
  let authenticating = false;
  let lastStartup = null;

  function issueTicket() {
    if (state !== "reconciled" || tickets.size >= MAX_TICKETS) return null;
    const ticket = Symbol("pdf-interception-restart-lifetime");
    tickets.add(ticket);
    return ticket;
  }

  function isCurrent(ticket) {
    return state === "reconciled" && tickets.has(ticket);
  }

  function release(ticket) {
    // Releasing a lifetime ticket is NOT a clean scan verdict.
    return state === "reconciled" && tickets.delete(ticket);
  }

  async function reconcileStartup(startup) {
    if (state === "disposed" || authenticating) return BLOCKED;

    let verify, revoke, cancel, snapshot;
    try {
      if (!exactRecord(startup, STARTUP_FIELDS) ||
          own(startup, "version") !== PDF_INTERCEPTION_RESTART_VERSION ||
          own(startup, "kind") !== "browser-startup" ||
          typeof own(startup, "browserId") !== "string" ||
          getPdfInterceptionPointAssessment(own(startup, "browserId")).browserId === null ||
          typeof own(startup, "startupId") !== "string" ||
          !ID.test(own(startup, "startupId")) ||
          seenStartups.size >= MAX_STARTUPS ||
          seenStartups.has(own(startup, "startupId"))) return BLOCKED;

      verify = own(coordinator, "verifyColdBrowserStartup");
      revoke = own(coordinator, "revokeHeldPdfInterceptions");
      cancel = own(coordinator, "cancelOrphanedPdfInterceptions");
      if ([verify, revoke, cancel].some(fn => typeof fn !== "function")) return BLOCKED;

      // Verification must complete synchronously, so no stale result can be
      // consumed during an await before the previous generation is revoked.
      authenticating = true;
      try {
        const proof = verify.call(coordinator, Object.freeze({
          browserId: own(startup, "browserId"), startupId: own(startup, "startupId")
        }));
        if (!exactRecord(proof, PROOF_FIELDS) ||
            own(proof, "kind") !== "verified-cold-browser-startup" ||
            own(proof, "verified") !== true ||
            own(proof, "browserId") !== own(startup, "browserId") ||
            own(proof, "startupId") !== own(startup, "startupId")) return BLOCKED;
        snapshot = Object.freeze({
          browserId: own(startup, "browserId"),
          startupId: own(startup, "startupId")
        });
        seenStartups.add(snapshot.startupId);
        // First invalidate: even synchronous re-entrancy in revoke/cancel
        // cannot use old tickets or register new work.
        generation++;
        tickets.clear();
        state = "reconciling";
        lastStartup = snapshot;
      } finally {
        authenticating = false;
      }
    } catch {
      return BLOCKED; // Never return exception text containing URLs or paths.
    }

    const epoch = generation;
    let revoked = false;
    try {
      // The coordinator must invalidate all held responses/scan callbacks
      // synchronously. A Promise is not acceptable for this first barrier.
      revoked = revoke.call(coordinator, snapshot) === true;
    } catch {
      // Still attempt native orphan cancellation after a revoke failure.
    }

    let cleared = false;
    try {
      const pending = cancel.call(coordinator, snapshot);
      if (pending && typeof pending.then === "function") {
        const answer = await pending;
        cleared = exactRecord(answer, CLEANUP_FIELDS) &&
          own(answer, "kind") === "native-orphaned-interceptions-cancelled" &&
          own(answer, "browserId") === snapshot.browserId &&
          own(answer, "startupId") === snapshot.startupId &&
          own(answer, "orphanedScansCancelled") === true;
      }
    } catch {
      // A missing/failed native ledger cleanup remains blocked.
    }

    if (state === "disposed" || generation !== epoch) {
      return result("unavailable", true);
    }
    if (!revoked || !cleared ||
        own(coordinator, "verifyColdBrowserStartup") !== verify ||
        own(coordinator, "revokeHeldPdfInterceptions") !== revoke ||
        own(coordinator, "cancelOrphanedPdfInterceptions") !== cancel) {
      state = "unavailable";
      return result("unavailable", true);
    }
    state = "reconciled";
    return result("orphan-cleanup-confirmed", true, true);
  }

  function dispose() {
    if (state === "disposed") return;
    generation++;
    tickets.clear();
    state = "disposed";
    if (lastStartup) {
      try {
        const revoke = own(coordinator, "revokeHeldPdfInterceptions");
        if (typeof revoke === "function") {
          Promise.resolve(revoke.call(coordinator, lastStartup)).catch(() => {});
        }
      } catch { /* terminally blocked regardless of cleanup errors */ }
    }
  }

  return Object.freeze({
    reconcileStartup, issueTicket, isCurrent, release, dispose,
    get status() { return state; }
  });
}
