// Opt-in native Port disconnect protection for a future trusted scan coordinator.
// Importing this module never connects a browser, starts a scan or opens a PDF.
// A connected transport does not authenticate the extension or verify a scan.
export function createNativeScanDisconnectGuard(port) {
  let event;
  try {
    event = port.onDisconnect;
    if (typeof event.addListener !== "function" ||
        typeof event.removeListener !== "function") {
      throw new TypeError();
    }
  } catch {
    throw new TypeError("Native scan disconnect observation is unavailable");
  }

  const active = new Map();
  let connected = true;

  function detach() {
    try {
      event.removeListener(onDisconnected);
    } catch {
      // A failed listener removal cannot re-enable disconnected scans.
    }
  }

  function onDisconnected() {
    if (!connected) return;
    // Latch and revoke all tokens before running any user-supplied callbacks.
    // A late completion or a re-entrant registration must now fail closed.
    connected = false;
    const cancellations = [...active.values()];
    active.clear();
    detach();
    for (const cancelScan of cancellations) {
      try {
        // Invoke synchronously so the trusted coordinator can abort promptly.
        // Also consume rejected cleanup promises without exposing error details.
        Promise.resolve(cancelScan()).catch(() => {});
      } catch {
        // Continue aborting other scans even if one cleanup callback fails.
      }
    }
  }

  try {
    event.addListener(onDisconnected);
    if (!connected) detach();
  } catch {
    onDisconnected();
    throw new TypeError("Native scan disconnect listener registration failed");
  }

  return Object.freeze({
    // Register only an already accepted, locally owned scan's cleanup action.
    // Opaque tokens prevent arbitrary caller-supplied scan IDs or PIDs.
    track(cancelScan) {
      if (!connected || typeof cancelScan !== "function") {
        throw new TypeError("Native scan connection is unavailable");
      }
      const token = Symbol("native-scan");
      active.set(token, cancelScan);
      return token;
    },
    // Check before using any asynchronous scan completion. This is a
    // liveness check ONLY, never a scanner verdict or opening authorization.
    isActive(token) {
      return connected && active.has(token);
    },
    // Forget successfully finished work so a later disconnect will not
    // cancel an already completed operation. The caller must separately
    // verify scanner evidence and enforce its PDF-opening security gates.
    release(token) {
      return connected && active.delete(token);
    },
    connectionLost() {
      return !connected;
    },
    // Explicit shutdown is equivalent to a disconnect, without invoking
    // port.disconnect() or changing browser permissions or preferences.
    dispose: onDisconnected
  });
}
