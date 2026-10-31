// Per-tab correlation only. This never starts scanning or authorizes opening.
export const MAX_CONCURRENT_PDF_TAB_SCANS = 64;
export const MAX_PDF_TAB_REQUEST_IDS = 4096;
const REQUEST_ID = /^[A-Za-z0-9_-]{1,80}$/u;

function identity(input) {
  try {
    if (input === null || typeof input !== "object" || Array.isArray(input) ||
        ![Object.prototype, null].includes(Object.getPrototypeOf(input))) return null;
    const keys = Reflect.ownKeys(input);
    if (keys.length !== 2 || !keys.includes("tabId") || !keys.includes("requestId")) return null;
    const tab = Object.getOwnPropertyDescriptor(input, "tabId");
    const request = Object.getOwnPropertyDescriptor(input, "requestId");
    if (!tab || !request || !Object.hasOwn(tab, "value") ||
        !Object.hasOwn(request, "value") ||
        !Number.isSafeInteger(tab.value) || tab.value < 0 ||
        typeof request.value !== "string" || !REQUEST_ID.test(request.value)) return null;
    return Object.freeze({ tabId: tab.value, requestId: request.value });
  } catch {
    // Never expose private metadata from malicious proxies and getters.
    return null;
  }
}

/**
 * A passive, bounded registry for independent simultaneous PDF tab scans.
 * A trusted caller must authenticate browser-owned tab IDs, bind cancellation
 * to the corresponding native scan, and recheck ticket validity after awaits.
 * Tickets NEVER prove scanner readiness, clean bytes, or permission to open.
 */
export function createPdfTabScanRegistry() {
  const byTab = new Map();
  const usedRequestIds = new Set();
  const ticketTabs = new WeakMap();
  let active = true;

  function isCurrent(ticket) {
    if (!active || ticket === null || typeof ticket !== "object") return false;
    const tabId = ticketTabs.get(ticket);
    return tabId !== undefined && byTab.get(tabId)?.ticket === ticket;
  }

  function cancel(entry) {
    try {
      // Async native cancellation failures cannot abort other invalidations.
      Promise.resolve(entry.cancelScan()).catch(() => {});
    } catch {
      // Never leak native paths or scanner diagnostics.
    }
  }

  function begin(details, cancelScan) {
    if (!active || typeof cancelScan !== "function") return null;
    const parsed = identity(details);
    if (!parsed || usedRequestIds.has(parsed.requestId) ||
        usedRequestIds.size >= MAX_PDF_TAB_REQUEST_IDS) return null;
    const previous = byTab.get(parsed.tabId);
    if (!previous && byTab.size >= MAX_CONCURRENT_PDF_TAB_SCANS) return null;

    const ticket = Object.freeze({
      tabId: parsed.tabId, requestId: parsed.requestId,
      scanVerified: false, authorizesScan: false, authorizesOpen: false
    });
    const entry = { ...parsed, ticket, cancelScan };
    // Install before callbacks so cancellation cannot resurrect stale scans.
    byTab.set(parsed.tabId, entry);
    usedRequestIds.add(parsed.requestId);
    ticketTabs.set(ticket, parsed.tabId);
    if (previous) cancel(previous);
    return ticket;
  }

  function complete(ticket) {
    if (!isCurrent(ticket)) return false;
    byTab.delete(ticketTabs.get(ticket));
    // This retires a session, NOT a native scan verification.
    return true;
  }

  function invalidateTab(tabId) {
    if (!active || !Number.isSafeInteger(tabId) || tabId < 0) return false;
    const entry = byTab.get(tabId);
    if (!entry) return false;
    byTab.delete(tabId);
    cancel(entry);
    return true;
  }

  function dispose() {
    if (!active) return;
    active = false;
    const entries = [...byTab.values()];
    byTab.clear();
    // Invalidate all tickets before invoking cancellation callbacks.
    for (const entry of entries) cancel(entry);
  }

  return Object.freeze({
    begin, isCurrent, complete, invalidateTab, dispose,
    get activeCount() { return active ? byTab.size : 0; }
  });
}
