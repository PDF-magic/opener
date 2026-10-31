// Passive, one-shot guard for a future authenticated PDF interception coordinator.
// This module never redirects, scans, opens, stores URLs or registers listeners.
export const PDF_INTERCEPTION_LOOP_GUARD_MAX_RESERVATIONS = 256;

const ID = /^[A-Za-z0-9_-]{1,80}$/u;
const REQUEST_FIELDS = Object.freeze(["requestId", "tabId", "frameId"]);
const NAVIGATION_FIELDS = Object.freeze([
  "requestId", "tabId", "frameId", "navigationId",
  "origin", "destination", "verified"
]);

function own(value, key) {
  if (value === null || (typeof value !== "object" &&
      typeof value !== "function")) return undefined;
  const descriptor = Object.getOwnPropertyDescriptor(value, key);
  return descriptor && Object.hasOwn(descriptor, "value") ?
    descriptor.value : undefined;
}

function exactRecord(value, fields) {
  if (value === null || typeof value !== "object" || Array.isArray(value) ||
      ![Object.prototype, null].includes(Object.getPrototypeOf(value))) {
    return false;
  }
  const keys = Reflect.ownKeys(value);
  return keys.length === fields.length &&
    keys.every(key => typeof key === "string" && fields.includes(key)) &&
    fields.every(key => {
      const descriptor = Object.getOwnPropertyDescriptor(value, key);
      return descriptor && Object.hasOwn(descriptor, "value");
    });
}

function outcome(status, suppressAutomaticInterception = true) {
  return Object.freeze({
    status, suppressAutomaticInterception, reservationRecorded:
      status === "reserved-for-independent-review",
    navigationRequested: false, scanVerified: false,
    authorizesScan: false, authorizesOpen: false
  });
}

const RESULT = Object.freeze({
  reserved: outcome("reserved-for-independent-review", false),
  duplicate: outcome("duplicate-navigation"),
  tab: outcome("tab-already-reserved"),
  owned: outcome("extension-or-pdfopener-route"),
  unverified: outcome("unverified-navigation"),
  capacity: outcome("capacity-exhausted"),
  ended: outcome("disposed")
});

/**
 * Reserve at most one automatic interception *attempt* per top-level tab,
 * plus one attempt per opaque request ID across tabs.
 *
 * A separately authenticated browser coordinator must own
 * readVerifiedNavigation(reference), returning a synchronous, exact snapshot
 * from browser-controlled state, not page scripts, URL parameters, referrers,
 * messages, or an untrusted claim of 'verified'. It must prove the current
 * top-frame document's provenance and destination. Only an external web -> web
 * PDF candidate may be considered. Extension-owned and PDFOpener-initiated
 * routes, unknown/opaque routes and redirects back into either are suppressed.
 *
 * Reservations are taken synchronously before any later navigation/scan work.
 * They are deliberately not released on failures, timeouts, new navigation
 * IDs or PDFOpener round-trips. Reuse ONE guard across all event listeners and
 * views; the future coordinator must persist suppressions across MV3 worker
 * restarts and handle verified tab closure without resetting an active loop.
 * This passive guard alone cannot authenticate browser events, stop other
 * opening paths, or ensure restart persistence.
 */
export function createPdfInterceptionNavigationLoopGuard(coordinator = null) {
  const tabs = new Set();
  const requests = new Set();
  let disposed = false;

  function reserveAttempt(reference) {
    if (disposed) return RESULT.ended;
    try {
      if (!exactRecord(reference, REQUEST_FIELDS)) return RESULT.unverified;
      const requestId = own(reference, "requestId");
      const tabId = own(reference, "tabId");
      const frameId = own(reference, "frameId");
      if (typeof requestId !== "string" || !ID.test(requestId) ||
          !Number.isSafeInteger(tabId) || tabId < 0 || frameId !== 0) {
        return RESULT.unverified;
      }

      // Deny replay before calling any coordinator-owned code. A tab remains
      // reserved across retries, redirect chains and changing navigation IDs.
      if (requests.has(requestId)) return RESULT.duplicate;
      if (tabs.has(tabId)) return RESULT.tab;
      if (requests.size >= PDF_INTERCEPTION_LOOP_GUARD_MAX_RESERVATIONS ||
          tabs.size >= PDF_INTERCEPTION_LOOP_GUARD_MAX_RESERVATIONS) {
        return RESULT.capacity;
      }

      const read = own(coordinator, "readVerifiedNavigation");
      if (own(coordinator, "loopGuardReady") !== true ||
          typeof read !== "function") return RESULT.unverified;
      const input = Object.freeze({ requestId, tabId, frameId });
      const snapshot = read.call(coordinator, input);
      if (!exactRecord(snapshot, NAVIGATION_FIELDS) ||
          own(snapshot, "requestId") !== requestId ||
          own(snapshot, "tabId") !== tabId ||
          own(snapshot, "frameId") !== frameId ||
          own(snapshot, "verified") !== true) return RESULT.unverified;

      const navigationId = own(snapshot, "navigationId");
      const origin = own(snapshot, "origin");
      const destination = own(snapshot, "destination");
      if (typeof navigationId !== "string" || !ID.test(navigationId) ||
          !["web", "extension", "pdfopener", "unknown"].includes(origin) ||
          !["web-pdf", "extension", "pdfopener", "unknown"].includes(destination)) {
        return RESULT.unverified;
      }
      if (origin !== "web" || destination !== "web-pdf") return RESULT.owned;

      // Recheck after a possibly reentrant verifier. Never evict an older
      // reservation or automatically clear one when navigation changes.
      if (disposed) return RESULT.ended;
      if (requests.has(requestId)) return RESULT.duplicate;
      if (tabs.has(tabId)) return RESULT.tab;
      if (requests.size >= PDF_INTERCEPTION_LOOP_GUARD_MAX_RESERVATIONS ||
          tabs.size >= PDF_INTERCEPTION_LOOP_GUARD_MAX_RESERVATIONS) {
        return RESULT.capacity;
      }
      requests.add(requestId);
      tabs.add(tabId);
      return RESULT.reserved;
    } catch {
      // Browser/native errors can contain private PDF URLs and file paths.
      return RESULT.unverified;
    }
  }

  function dispose() {
    if (disposed) return RESULT.ended;
    disposed = true;
    requests.clear();
    tabs.clear();
    return RESULT.ended;
  }

  return Object.freeze({ reserveAttempt, dispose });
}
