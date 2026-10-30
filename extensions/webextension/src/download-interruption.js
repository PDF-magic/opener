import { subscribeToDownloadEvents } from "./download-monitoring.js";

// Browser interruption is not a scan result, reason to retry, or authority
// to read or open a file. Importing this module never attaches listeners.
const MAX_REMEMBERED_IDS = 256;

/**
 * Observe browser-reported interruptions only after a trusted caller has
 * separately verified optional downloads permission and user consent.
 * Notifications contain an ID, never untrusted paths, URLs, errors or bytes.
 */
export function subscribeToDownloadInterruptions(downloadsApi, onInterrupted, { onError } = {}) {
  if (typeof onInterrupted !== "function") {
    throw new TypeError("An interruption callback is required");
  }

  const interrupted = new Set();
  const unsubscribe = subscribeToDownloadEvents(downloadsApi, (event) => {
    if (event.kind === "created" || event.kind === "erased" ||
        (event.kind === "changed" && event.state === "in_progress")) {
      // Downloads may resume or reuse IDs: permit a new interruption.
      interrupted.delete(event.id);
      return;
    }
    if (event.kind !== "changed" || event.state !== "interrupted" ||
        interrupted.has(event.id)) return;

    if (interrupted.size >= MAX_REMEMBERED_IDS) {
      interrupted.delete(interrupted.values().next().value);
    }
    interrupted.add(event.id);
    onInterrupted(Object.freeze({ kind: "interrupted", id: event.id }));
  }, { onError });

  let active = true;
  return function unsubscribeInterruptions() {
    if (!active) return;
    active = false;
    unsubscribe();
    interrupted.clear();
  };
}
