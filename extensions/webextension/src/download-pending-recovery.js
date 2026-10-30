import { subscribeToDownloadEvents } from "./download-monitoring.js";
import { createNativeScanDisconnectGuard } from "./native-scan-disconnect.js";

// Session-local, fail-closed recovery for accepted native scan submissions.
// An interrupted or unknown request is abandoned, NEVER automatically
// replayed. Native scan cancellation and final opening remain authoritative.
const MAX_PENDING = 256;
const SCAN_ID = /^[A-Za-z0-9_-]{1,80}$/u;
const outcomes = Object.freeze({
  pending: Object.freeze({
    status: "pending", scanVerified: false, authorizesOpen: false
  }),
  unavailable: Object.freeze({
    status: "unavailable", scanVerified: false, authorizesOpen: false
  })
});

function own(value, key) {
  if (value === null || typeof value !== "object") return undefined;
  const descriptor = Object.getOwnPropertyDescriptor(value, key);
  return descriptor && Object.hasOwn(descriptor, "value") ? descriptor.value : undefined;
}

function submissionId(value) {
  try {
    if (value === null || typeof value !== "object" ||
        Array.isArray(value) ||
        ![Object.prototype, null].includes(Object.getPrototypeOf(value))) return null;
    const fields = ["status", "id", "scanSubmitted", "scanVerified", "authorizesOpen"];
    const actual = Reflect.ownKeys(value);
    if (actual.length !== fields.length ||
        !fields.every((field) => actual.includes(field))) return null;
    const id = own(value, "id");
    return own(value, "status") === "submitted" &&
      own(value, "scanSubmitted") === true &&
      own(value, "scanVerified") === false &&
      own(value, "authorizesOpen") === false &&
      Number.isSafeInteger(id) && id >= 0 ? id : null;
  } catch {
    return null;
  }
}

function validScanId(value) {
  return typeof value === "string" && SCAN_ID.test(value);
}

/**
 * A separately authenticated trusted native coordinator must explicitly
 * install this observer with its own Port and download-event source. A
 * scanner acceptance must already have been verified separately. The
 * cancellation callback is session-owned native cleanup, not a browser API.
 *
 * Browser interruption, erasure, ID reuse, download danger/error/rename
 * changes, Port disconnect and explicit shutdown revoke pending scan tokens
 * before invoking native cleanup. Nothing here resumes or opens a PDF.
 */
export function createPendingDownloadScanRecovery(downloadsApi, nativePort) {
  const pending = new Map();
  const byDownload = new Map();
  const byScan = new Map();
  const abandonedIds = new Set();
  let active = true;
  let unsubscribe = null;
  const guard = createNativeScanDisconnectGuard(nativePort);

  function forget(token) {
    const entry = pending.get(token);
    if (!entry) return null;
    pending.delete(token);
    byDownload.delete(entry.id);
    byScan.delete(entry.scanRequestId);
    guard.release(entry.guardToken);
    return entry;
  }

  function cancelSafely(entry) {
    try {
      Promise.resolve(entry.cancel()).catch(() => {});
    } catch {
      // Best-effort cleanup may fail; it never restores a revoked token.
    }
  }

  function abandon(token) {
    const entry = forget(token);
    if (!entry) return false;
    abandonedIds.add(entry.id);
    cancelSafely(entry);
    return true;
  }

  function abandonDownload(id) {
    const token = byDownload.get(id);
    if (token !== undefined) abandon(token);
  }

  function onDownload(event) {
    if (!active) return;
    if (event.kind === "created") {
      // Only a new observed lifecycle permits reusing a browser ID.
      abandonDownload(event.id);
      abandonedIds.delete(event.id);
      return;
    }
    if (event.kind === "erased") {
      abandonDownload(event.id);
      abandonedIds.add(event.id);
      return;
    }
    if (event.kind === "changed" &&
        (event.state === "interrupted" ||
         (event.state !== undefined && event.state !== "complete") ||
         event.error !== undefined || event.filename !== undefined ||
         event.danger !== undefined)) {
      abandonDownload(event.id);
      abandonedIds.add(event.id);
    }
  }

  try {
    unsubscribe = subscribeToDownloadEvents(downloadsApi, onDownload);
  } catch {
    guard.dispose();
    throw new TypeError("Download recovery requires a complete event source");
  }

  /**
   * Track only a previously accepted, exact-ID native scan request. The
   * scanRequestId is an opaque coordinator-owned ID, not a path or URL.
   * No callbacks are run when registration is invalid or at capacity.
   */
  function track(submission, scanRequestId, cancelPendingScan) {
    const id = submissionId(submission);
    if (!active || guard.connectionLost() || id === null ||
        !validScanId(scanRequestId) ||
        typeof cancelPendingScan !== "function" ||
        pending.size >= MAX_PENDING || abandonedIds.size >= MAX_PENDING ||
        abandonedIds.has(id) || byDownload.has(id) ||
        byScan.has(scanRequestId)) return null;

    const token = Symbol("pending-download-scan");
    const entry = {
      id, scanRequestId, cancel: cancelPendingScan, guardToken: null
    };
    // The native guard invokes this cancellation synchronously upon Port
    // loss. Do not leave a window for a late result to be considered active.
    try {
      entry.guardToken = guard.track(() => { abandon(token); });
    } catch {
      return null;
    }
    pending.set(token, entry);
    byDownload.set(id, token);
    byScan.set(scanRequestId, token);
    if (!active || guard.connectionLost()) {
      abandon(token);
      return null;
    }
    return token;
  }

  function state(token) {
    return active && !guard.connectionLost() && pending.has(token)
      ? outcomes.pending : outcomes.unavailable;
  }

  function release(token) {
    // Only forget a pending operation. This does NOT validate scan evidence,
    // authorize opening, or permit a second request for the same download.
    const entry = forget(token);
    if (!entry) return false;
    abandonedIds.add(entry.id);
    return true;
  }

  function dispose() {
    if (!active) return;
    active = false;
    try { unsubscribe?.(); } catch { /* already fail closed */ }
    for (const token of [...pending.keys()]) abandon(token);
    guard.dispose();
    abandonedIds.clear();
  }

  return Object.freeze({ track, state, release, abandon, dispose });
}
