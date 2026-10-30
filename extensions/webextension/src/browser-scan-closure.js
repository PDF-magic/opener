import { createNativeScanDisconnectGuard } from "./native-scan-disconnect.js";

// Passive fail-closed lifetime adapter for an independently authenticated
// scan session. No global browser APIs or native scanner invocation.
function own(value, key) {
  if (value === null || typeof value !== "object") return undefined;
  const descriptor = Object.getOwnPropertyDescriptor(value, key);
  return descriptor && Object.hasOwn(descriptor, "value") ? descriptor.value : undefined;
}

/**
 * Protect already-accepted native scan jobs against browser closure.
 *
 * Native Port disconnect is the fallback when the browser terminates without
 * runtime.onSuspend. On worker suspension, invalidate all tracked tokens
 * before invoking cancellation callbacks. Browser suspension can happen
 * without a full browser quit; stopping in that case is intentionally safe.
 *
 * Every callback MUST cancel and reap its own native job. No JavaScript
 * handler can guarantee cleanup after an abrupt browser process death.
 */
export function createBrowserScanClosureGuard(port, lifecycle = null) {
  const suspend = lifecycle === null ? null : own(lifecycle, "onSuspend");
  const add = suspend === null ? null : own(suspend, "addListener");
  const remove = suspend === null ? null : own(suspend, "removeListener");
  if (lifecycle !== null && (typeof add !== "function" ||
      typeof remove !== "function")) {
    throw new TypeError("Browser shutdown observation is unavailable");
  }

  // Existing native transport is required; connection is not authentication.
  const nativeGuard = createNativeScanDisconnectGuard(port);
  let active = true;
  let registered = false;

  function stop() {
    if (!active) return;
    active = false;
    nativeGuard.dispose();
    if (suspend !== null && registered) {
      try { remove.call(suspend, stop); } catch {
        // Cleanup failure must never reactivate a scan.
      }
    }
  }

  try {
    if (suspend !== null) {
      registered = true;
      add.call(suspend, stop);
      if (!active) {
        try { remove.call(suspend, stop); } catch { /* no restart */ }
      }
    }
  } catch {
    stop();
    throw new TypeError("Browser shutdown listener registration failed");
  }

  return Object.freeze({
    track(cancelScan) {
      if (!active || nativeGuard.connectionLost()) {
        throw new TypeError("Browser scan session is unavailable");
      }
      return nativeGuard.track(cancelScan);
    },
    // Recheck before consuming any asynchronous scanner result. New sessions
    // cannot reuse old opaque tokens, nor can a clean verdict authorize open.
    isActive(token) { return active && nativeGuard.isActive(token); },
    release(token) { return active && nativeGuard.release(token); },
    connectionLost() { return !active || nativeGuard.connectionLost(); },
    dispose: stop
  });
}
