// Fail-closed response to permission denials (opener-0589).
// An explicit caller supplies a result and its existing feature shutdown hook.
// No browser permissions, listeners, native messages, scans or settings changes
// occur when this module is imported or a handler is constructed.

export const PERMISSION_DENIAL_MESSAGES = Object.freeze({
  unverified: "Permission has not been verified. This feature remains unavailable.",
  denied: "Permission was not granted. This feature remains unavailable. You can choose to try again later.",
  unavailable: "Permission could not be verified. This feature remains unavailable.",
  cleanupFailed: "Permission is unavailable and feature shutdown could not be confirmed. Restart the extension before trying again."
});

const states = Object.freeze(Object.fromEntries([
  ["unverified", "unverified"],
  ["denied", "denied"],
  ["unavailable", "unavailable"],
  ["cleanup-failed", "cleanupFailed"]
].map(([status, messageKey]) => [status, Object.freeze({
  status,
  message: PERMISSION_DENIAL_MESSAGES[messageKey],
  canProceed: false,
  scannerVerified: false,
  authorizesOpen: false
})])));

function isExplicitDenial(result) {
  if (result === false) return true;
  if (result === null || typeof result !== "object") return false;
  try {
    const descriptor = Object.getOwnPropertyDescriptor(result, "status");
    return descriptor !== undefined && "value" in descriptor &&
      descriptor.value === "denied";
  } catch {
    return false;
  }
}

/**
 * Build a dormant denial handler for a specific, separately implemented
 * protected feature (e.g. download monitoring or optional site access).
 *
 * Pass the caller's cleanup function to stop the feature on an explicit
 * denial or an unknown/unverifiable permission result. A rejection is latched
 * until the caller starts a fresh, user-initiated permission flow with a new
 * handler; this module never prompts, retries or persists preferences.
 *
 * Successful permission results are intentionally NOT interpreted as scan
 * approval or authorization to start anything. The feature owner must verify
 * current grants and scanner gates independently before enabling work.
 *
 * @param {function(): (void|Promise<void>)|null} stopProtectedFeature
 */
export function createPermissionDenialHandler(stopProtectedFeature = null) {
  if (stopProtectedFeature !== null &&
      typeof stopProtectedFeature !== "function") {
    throw new TypeError("A shutdown function is required for denial cleanup");
  }

  let current = states.unverified;
  let pending = null;
  let handled = false;

  function state() {
    return current;
  }

  function handle(result) {
    if (handled) return pending ?? Promise.resolve(current);
    // This is a *denial* handler, not a permission granting API. A positive
    // outcome is deliberately left unverified here.
    if (result === true) return Promise.resolve(current);

    handled = true; // Latch before invoking shutdown: a reentrant call cannot repeat it.
    current = isExplicitDenial(result) ? states.denied : states.unavailable;
    pending = (async () => {
      try {
        // Shutdown starts in the same turn, before this function awaits.
        // No permission request or browser global access is made here.
        if (stopProtectedFeature) await stopProtectedFeature();
      } catch {
        // A failed cleanup can leave registered handlers in place. Report
        // uncertainty without passing raw paths or errors to the UI.
        current = states["cleanup-failed"];
      }
      return current;
    })();
    return pending;
  }

  return Object.freeze({ state, handle });
}
