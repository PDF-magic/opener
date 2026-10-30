// Passive desktop-application lifetime protection for download scans.
// Only a separately authenticated native coordinator may provide this event.
// It is NOT a browser window lifecycle event or a scanner authorization.
const unavailable = Object.freeze({
  status: "unavailable", scanVerified: false, authorizesOpen: false
});

function own(value, key) {
  if (value === null || (typeof value !== "object" && typeof value !== "function")) {
    return undefined;
  }
  const descriptor = Object.getOwnPropertyDescriptor(value, key);
  return descriptor && Object.hasOwn(descriptor, "value")
    ? descriptor.value : undefined;
}

/**
 * A download-scanning session must stop when the native desktop application
 * that owns it closes, even if the browser Port remains connected.
 *
 * The native coordinator MUST independently authenticate the application
 * lifecycle and terminate its owned scanner process group upon cancellation.
 * A readiness flag or event emitter by itself is not authentication.
 * This adapter only revokes in-flight tokens and invokes their already
 * registered, trusted cancellation callbacks. It never starts a scan.
 */
export function createDownloadDesktopClosureGuard(coordinator) {
  let event;
  let add;
  let remove;
  try {
    if (own(coordinator, "nativeDesktopLifecycleReady") !== true) throw new TypeError();
    event = own(coordinator, "onDesktopApplicationClosed");
    add = own(event, "addListener");
    remove = own(event, "removeListener");
    if (typeof add !== "function" || typeof remove !== "function") throw new TypeError();
  } catch {
    throw new TypeError("Trusted desktop application lifecycle is unavailable");
  }

  const active = new Map();
  let applicationAlive = true;
  let subscribed = false;

  function detach() {
    if (!subscribed) return;
    subscribed = false;
    try { remove.call(event, onClosed); }
    catch { /* Never restore a closed session after failed cleanup. */ }
  }

  function onClosed() {
    if (!applicationAlive) return;
    // Revoke every token before any callback can reenter the guard.
    applicationAlive = false;
    const callbacks = [...active.values()];
    active.clear();
    detach();
    for (const cancelScan of callbacks) {
      try {
        // Invoke synchronously so the native owner can abort immediately.
        // Async cleanup failures must not escape or skip other scans.
        Promise.resolve(cancelScan()).catch(() => {});
      } catch {
        // Continue canceling the rest; never expose paths or native errors.
      }
    }
  }

  try {
    // A coordinator may synchronously announce closure during registration.
    // Preserve that closed state even if the event is delivered immediately.
    subscribed = true;
    add.call(event, onClosed);
    if (!applicationAlive) detach();
  } catch {
    onClosed();
    throw new TypeError("Desktop application lifecycle listener registration failed");
  }

  return Object.freeze({
    track(cancelScan) {
      if (!applicationAlive || typeof cancelScan !== "function") {
        throw new TypeError("Desktop application scan session is unavailable");
      }
      const token = Symbol("desktop-owned-download-scan");
      active.set(token, cancelScan);
      return token;
    },
    isActive(token) {
      return applicationAlive && active.has(token);
    },
    release(token) {
      return applicationAlive && active.delete(token);
    },
    applicationClosed() {
      return !applicationAlive;
    },
    // Consume an asynchronous result only while this native owner remains
    // alive and the token is still tracked. The result remains UNVERIFIED:
    // the caller must independently enforce all native scan/open safety gates.
    async receive(token, pending) {
      try {
        if (!applicationAlive || !active.has(token) ||
            !pending || typeof pending.then !== "function") return unavailable;
        const result = await pending;
        if (!applicationAlive || !active.has(token)) return unavailable;
        return result;
      } catch {
        return unavailable;
      }
    },
    // Explicit owner shutdown has the same fail-closed effects as the event.
    dispose: onClosed
  });
}
