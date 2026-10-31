// Passive holding-screen history guard for future optional PDF interception.
// No browser history edits, navigation listeners, permissions or scanner access.
const ENTRY_ID = /^[A-Za-z0-9_-]{1,80}$/u;
const FIELDS = ["tabId", "holdingEntryId", "cancelPendingScan"];
const EVENT_FIELDS = ["tabId", "frameId", "leavingEntryId", "direction", "verified"];

function own(value, key) {
  if (value === null || typeof value !== "object") return undefined;
  const descriptor = Object.getOwnPropertyDescriptor(value, key);
  return descriptor && Object.hasOwn(descriptor, "value") ? descriptor.value : undefined;
}

function exactRecord(value, fields) {
  try {
    if (value === null || typeof value !== "object" || Array.isArray(value) ||
        ![Object.prototype, null].includes(Object.getPrototypeOf(value))) return false;
    const keys = Reflect.ownKeys(value);
    return keys.length === fields.length &&
      keys.every(key => typeof key === "string" && fields.includes(key)) &&
      fields.every(key => Object.hasOwn(Object.getOwnPropertyDescriptor(value, key), "value"));
  } catch {
    return false;
  }
}

function report(status, active, cancelRequested = false) {
  return Object.freeze({
    status, holdingActive: active, cancelRequested,
    // Browser Back must remain the browser's normal history traversal.
    historyMutationRequested: false, navigationRequested: false,
    skipHoldingRedirect: !active, autoResumeOnForward: false,
    // An attempted cancel is not proof of native cancellation or a clean scan.
    cancelConfirmed: false, authorizesScan: false, authorizesOpen: false
  });
}

/**
 * One guard per verified holding-page entry, created by a future trusted host.
 * The host must normalize actual browser history transitions: the browser's
 * forward_back qualifier alone cannot distinguish Back from Forward.
 * An untrusted webpage may not supply verified events. Use onPageExit() as a
 * fail-closed pagehide/tab-close fallback when direction cannot be known.
 *
 * The callback only requests cancellation of the session's pending scan;
 * native enforcement and verified open-gating stay outside this module.
 */
export function createPdfInterceptionBackNavigationGuard(options) {
  if (!exactRecord(options, FIELDS) ||
      !Number.isSafeInteger(own(options, "tabId")) || own(options, "tabId") < 0 ||
      typeof own(options, "holdingEntryId") !== "string" ||
      !ENTRY_ID.test(own(options, "holdingEntryId")) ||
      typeof own(options, "cancelPendingScan") !== "function") {
    throw new TypeError("Verified holding-session coordination is required");
  }

  const tabId = own(options, "tabId");
  const entryId = own(options, "holdingEntryId");
  const cancel = own(options, "cancelPendingScan");
  let active = true;

  function leave(status) {
    if (!active) return report("already-left", false);
    // Invalidate before invoking external cancellation (including reentry).
    active = false;
    try {
      const pending = cancel();
      // An asynchronous cancellation failure cannot revive a stale session.
      if (pending && typeof pending.then === "function") {
        Promise.resolve(pending).catch(() => {});
      }
    } catch {
      // Native cancellation is best-effort, never a scan/open approval.
    }
    return report(status, false, true);
  }

  return Object.freeze({
    onHistoryNavigation(event) {
      if (!active) return report("already-left", false);
      if (!exactRecord(event, EVENT_FIELDS) ||
          own(event, "verified") !== true ||
          own(event, "tabId") !== tabId || own(event, "frameId") !== 0 ||
          own(event, "leavingEntryId") !== entryId ||
          !["back", "forward"].includes(own(event, "direction"))) {
        return report("unverified-history-event", true);
      }
      return leave(own(event, "direction") === "back" ?
        "back-navigation" : "forward-navigation");
    },
    // A leaving holding page must not keep a scan alive if the platform has
    // no reliable history direction event (BFCache, reload, tab close, etc.).
    onPageExit() { return leave("page-exit"); },
    // Returning via Forward/BFCache does not recreate consent or replay scans.
    onPageRestore() {
      return report(active ? "still-holding" : "stale-holding-entry", active);
    },
    isCurrentHoldingEntry() { return active; },
    dispose() { return leave("disposed"); }
  });
}
