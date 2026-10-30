import { subscribeToDownloadEvents } from "./download-monitoring.js";

// Cancellation is a specific browser interruption reason, not a PDF verdict.
const MAX_REMEMBERED_IDS = 256;

/**
 * Passively detect downloads.onChanged error.current === "USER_CANCELED".
 * A generic interrupted state, USER_SHUTDOWN and history erasure are not
 * cancellation evidence. Only a trusted, opted-in and permission-verified
 * caller may invoke this; importing the module has no effects.
 */
export function subscribeToDownloadCancellations(downloadsApi, onCancelled, { onError } = {}) {
  if (typeof onCancelled !== "function") {
    throw new TypeError("A cancellation callback is required");
  }

  const reported = new Set();
  const reportError = () => {
    try { onError?.(new Error("Download cancellation callback failed")); }
    catch { /* do not propagate callback or error-handler details */ }
  };
  const unsubscribe = subscribeToDownloadEvents(downloadsApi, (event) => {
    if (event.kind === "created" || event.kind === "erased") {
      // Browser IDs can be reused; never retain paths, URLs or metadata.
      reported.delete(event.id);
      return;
    }
    if (event.kind !== "changed" || event.error !== "USER_CANCELED" ||
        reported.has(event.id)) return;

    if (reported.size >= MAX_REMEMBERED_IDS) {
      reported.delete(reported.values().next().value);
    }
    reported.add(event.id);
    // The browser ID cannot authorize scanning, quarantine or opening.
    onCancelled(Object.freeze({ kind: "cancelled", id: event.id }));
  }, { onError: reportError });

  let active = true;
  return function unsubscribeCancellations() {
    if (!active) return;
    active = false;
    unsubscribe();
    reported.clear();
  };
}
