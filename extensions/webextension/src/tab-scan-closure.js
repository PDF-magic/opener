// Passive, opt-in cancellation of already accepted native scans when their
// originating browser tab closes. No tabs listener is installed on import.
const MAX_CLOSED_TABS = 4096;
const unavailable = Object.freeze({
  status: "unavailable", scanVerified: false, authorizesOpen: false
});

function own(value, key) {
  if (value === null || (typeof value !== "object" && typeof value !== "function")) {
    return undefined;
  }
  const descriptor = Object.getOwnPropertyDescriptor(value, key);
  return descriptor && Object.hasOwn(descriptor, "value") ? descriptor.value : undefined;
}

function validTabId(tabId) {
  return Number.isSafeInteger(tabId) && tabId >= 0;
}

/**
 * Observe a trusted, privileged tabs.onRemoved source for a future authenticated
 * browser-to-native scan coordinator. The caller must verify the scan's actual
 * originating tab and own a cancel-and-reap callback for each accepted job.
 * An event source or token alone never authenticates a scan or permits opening.
 */
export function createTabScanClosureGuard(tabs) {
  let event, add, remove;
  try {
    event = own(tabs, "onRemoved");
    add = own(event, "addListener");
    remove = own(event, "removeListener");
  } catch {
    throw new TypeError("Trusted tab closure observation is unavailable");
  }
  if (typeof add !== "function" || typeof remove !== "function") {
    throw new TypeError("Trusted tab closure observation is unavailable");
  }

  const jobs = new Map();
  const closedTabs = new Set();
  let disposed = false;
  let subscribed = false;

  function cancelAll(callbacks) {
    for (const cancelScan of callbacks) {
      try {
        // Invalidate tokens before calling native-owned cancellation actions.
        Promise.resolve(cancelScan()).catch(() => {});
      } catch {
        // Failure to reap one job cannot prevent cancellation of another.
      }
    }
  }

  function detach() {
    if (!subscribed) return;
    subscribed = false;
    try { remove.call(event, onRemoved); }
    catch { /* Listener failures never restore scan authorization. */ }
  }

  function dispose() {
    if (disposed) return;
    disposed = true;
    const callbacks = [...jobs.values()].map(job => job.cancelScan);
    jobs.clear();
    closedTabs.clear();
    detach();
    cancelAll(callbacks);
  }

  function onRemoved(tabId) {
    if (disposed) return;
    // An invalid event from a supposedly privileged source invalidates the
    // entire session. Never silently leave native jobs running on bad input.
    if (!validTabId(tabId)) {
      dispose();
      return;
    }
    if (closedTabs.has(tabId)) return;
    if (closedTabs.size >= MAX_CLOSED_TABS) {
      dispose();
      return;
    }
    closedTabs.add(tabId);
    const callbacks = [];
    for (const [token, job] of jobs) {
      if (job.tabId !== tabId) continue;
      jobs.delete(token);
      callbacks.push(job.cancelScan);
    }
    cancelAll(callbacks);
  }

  try {
    subscribed = true;
    add.call(event, onRemoved);
    // An event can be emitted synchronously during listener registration.
    if (disposed) {
      try { remove.call(event, onRemoved); } catch { /* fail closed */ }
    }
  } catch {
    dispose();
    throw new TypeError("Tab closure listener registration failed");
  }

  return Object.freeze({
    track(tabId, cancelScan) {
      if (disposed || !validTabId(tabId) || closedTabs.has(tabId) ||
          typeof cancelScan !== "function") {
        throw new TypeError("Tab scan session is unavailable");
      }
      const token = Symbol("tab-owned-native-scan");
      jobs.set(token, { tabId, cancelScan });
      return token;
    },
    isActive(token) { return !disposed && jobs.has(token); },
    release(token) { return !disposed && jobs.delete(token); },
    tabClosed(tabId) { return disposed || closedTabs.has(tabId); },
    // Late scanner results are non-actionable after tab closure. A live result
    // still requires the existing independent native verification/open gates.
    async receive(token, pending) {
      try {
        if (disposed || !jobs.has(token) ||
            !pending || typeof pending.then !== "function") return unavailable;
        const result = await pending;
        return !disposed && jobs.has(token) ? result : unavailable;
      } catch {
        return unavailable;
      }
    },
    dispose
  });
}
