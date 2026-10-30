// A single authenticated native scan session must never receive repeated
// opening commands for the same scan request. A future trusted coordinator
// owns this passive, in-memory gate; importing it does not register listeners,
// contact native messaging, inspect files, or enable an installed browser UI.
const REQUEST_ID = /^[A-Za-z0-9_-]{1,80}$/u;
const MAX_RESERVED_REQUESTS = 256;

const outcomes = Object.freeze({
  unavailable: Object.freeze({
    status: "unavailable", scanVerified: false, authorizesOpen: false, opened: false
  }),
  duplicate: Object.freeze({
    status: "duplicate", scanVerified: false, authorizesOpen: false, opened: false
  }),
  capacity: Object.freeze({
    status: "capacity-exhausted", scanVerified: false, authorizesOpen: false, opened: false
  }),
  rejected: Object.freeze({
    status: "command-rejected", scanVerified: false, authorizesOpen: false, opened: false
  }),
  submitted: Object.freeze({
    status: "command-submitted", scanVerified: false, authorizesOpen: false, opened: false
  })
});

function ownData(value, name) {
  if (value === null || (typeof value !== "object" && typeof value !== "function")) {
    return undefined;
  }
  const descriptor = Object.getOwnPropertyDescriptor(value, name);
  return descriptor && Object.hasOwn(descriptor, "value") ? descriptor.value : undefined;
}

/**
 * Reserve at most one opening command per locally owned native scan request.
 *
 * Construct ONE gate for the lifetime of an authenticated scanner session,
 * and reuse it across all trusted UI views and open-after-scan retries.
 * The native coordinator MUST independently authenticate the scan session,
 * validate the user's opening intent, and enforce a completed clean ClamAV
 * scan, fresh signatures, unchanged local file, quarantine and the selected
 * destination application before performing any open. This JavaScript gate
 * cannot authenticate those conditions and never declares opening authorized.
 *
 * requestOpenOnce() reserves the ID synchronously BEFORE invoking the trusted
 * coordinator-supplied callback. Failed, rejected, pending and successful
 * callbacks ALL consume that ID: retrying a possibly dispatched command
 * could open twice. The callback receives no path, URL, browser metadata,
 * verifier flags or scanner results from this gate. A valid acknowledgement
 * means only that a command was submitted, NOT that scanning or opening
 * succeeded. There is no eviction or implicit reset on browser events.
 */
export function createDownloadOpenCommandGate() {
  const reserved = new Set();
  let active = true;

  async function requestOpenOnce(scanRequestId, issueOpenCommand) {
    if (!active || typeof scanRequestId !== "string" ||
        !REQUEST_ID.test(scanRequestId) || typeof issueOpenCommand !== "function") {
      return outcomes.unavailable;
    }
    if (reserved.has(scanRequestId)) return outcomes.duplicate;
    if (reserved.size >= MAX_RESERVED_REQUESTS) return outcomes.capacity;

    // Synchronous reservation prevents concurrent and reentrant submissions.
    reserved.add(scanRequestId);
    try {
      const pending = issueOpenCommand();
      if (!pending || typeof pending.then !== "function") return outcomes.rejected;
      const acknowledgement = await pending;
      if (!active || ownData(acknowledgement, "accepted") !== true) {
        return outcomes.rejected;
      }
      return outcomes.submitted;
    } catch {
      // Never echo native diagnostics, file paths, URLs or arbitrary errors.
      return outcomes.rejected;
    }
  }

  function dispose() {
    if (!active) return;
    active = false;
    reserved.clear();
  }

  return Object.freeze({ requestOpenOnce, dispose });
}
