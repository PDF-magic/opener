import { subscribeToDownloadEvents } from "./download-monitoring.js";

// Browser completion means transfer state only. It is not a scan verdict,
// permission to open the file, or evidence that a downloaded path is safe.
const MAX_REMEMBERED_IDS = 256;

/**
 * Subscribe to completion transitions using the existing opt-in download
 * event adapter. The caller must independently verify downloads permission
 * and user consent before calling this function; importing it has no effects.
 *
 * A completion is reported only when downloads.onChanged carries a current
 * state of exactly "complete". Creation, filename/danger-only changes, prior
 * state values, interrupted downloads and duplicate completions do not signal.
 * Only numeric download IDs are retained, with bounded duplicate suppression.
 */
export function subscribeToDownloadCompletions(downloadsApi, onCompleted, { onError } = {}) {
  if (typeof onCompleted !== "function") {
    throw new TypeError("A completion callback is required");
  }

  const completed = new Set();
  const unsubscribe = subscribeToDownloadEvents(downloadsApi, (event) => {
    if (event.kind === "created" || event.kind === "erased") {
      // Browser IDs can be reused. Never retain filenames or URLs.
      completed.delete(event.id);
      return;
    }
    if (event.kind !== "changed" || event.state !== "complete" ||
        completed.has(event.id)) return;

    if (completed.size >= MAX_REMEMBERED_IDS) {
      completed.delete(completed.values().next().value);
    }
    completed.add(event.id);
    // Detached immutable notification; no browser metadata, scanner verdict,
    // filesystem path, PDF opening request, or download contents are emitted.
    onCompleted(Object.freeze({ kind: "completed", id: event.id }));
  }, { onError });

  let active = true;
  return function unsubscribeCompletions() {
    if (!active) return;
    active = false;
    unsubscribe();
    completed.clear();
  };
}
