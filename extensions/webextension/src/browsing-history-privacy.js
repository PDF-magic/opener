// Privacy-preserving view of explicitly subscribed download activity (opener-0595).
// No browsing history, download identifiers, filenames, URLs, timestamps,
// origins or metadata are retained or forwarded by this adapter.
// No subscriptions, storage operations or browser API calls occur on import.
import { subscribeToDownloadEvents } from "./download-monitoring.js";

// Reuse three immutable category-only signals. Per-download records, IDs,
// timestamps, paths and origin information never become state in this module.
// These signals are neither scanning verdicts nor PDF-opening authorization.
const signals = Object.freeze(Object.fromEntries(
  ["created", "changed", "erased"].map((kind) => [
    kind, Object.freeze({ kind, authorizesOpen: false })
  ])
));

/**
 * Subscribe only when a separately authorized caller enables monitoring.
 * This deliberately exposes less data than subscribeToDownloadEvents:
 * the callback sees only one frozen activity category, never a record that
 * could be correlated into a per-site or per-download browsing history.
 *
 * No events are stored, replayed, queued, timestamped or sent elsewhere.
 * Explicit unsubscribe detaches every browser listener; the lower-level
 * adapter also rolls back partial registration and isolates callback errors.
 *
 * This does not request the optional downloads permission, activate the
 * existing no-op background, retain preferences, or authorize any scan/open.
 * Future callers must still check effective permission, obtain consent,
 * avoid storing a time series themselves and stop on permission revocation.
 */
export function subscribeToHistoryFreeDownloadActivity(
  downloadsApi,
  onActivity,
  options = {}
) {
  if (typeof onActivity !== "function") {
    throw new TypeError("An activity callback is required");
  }
  return subscribeToDownloadEvents(downloadsApi, (event) => {
    const signal = signals[event.kind];
    if (signal) onActivity(signal);
  }, options);
}
