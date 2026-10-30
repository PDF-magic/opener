import { describeExplicitPdfScanRequest } from "./explicit-pdf-scan-request.js";
import { subscribeToDownloadEvents } from "./download-monitoring.js";

// A deadline applies to a separately authenticated, explicitly started PDF
// transfer. Importing this module does not observe browser events or run timers.
export const EXPLICIT_PDF_DOWNLOAD_TIMEOUT_MS = 120_000;
export const MAX_EXPLICIT_PDF_DOWNLOAD_TIMEOUT_MS = 300_000;

const ID = /^[A-Za-z0-9_-]{1,80}$/u;
const FIELDS = Object.freeze([
  "requestId", "downloadId", "selectionId", "tabId", "frameId",
  "startedAtMs", "state", "verified", "permissionGranted"
]);
const MAX_ATTEMPTS = 128;
const MAX_ACTIVE = 32;
const TERMINAL = Object.freeze([
  "completed", "timed-out", "interrupted", "unavailable", "disposed"
]);

function own(value, key) {
  if (value === null || (typeof value !== "object" && typeof value !== "function")) {
    return undefined;
  }
  const descriptor = Object.getOwnPropertyDescriptor(value, key);
  return descriptor && Object.hasOwn(descriptor, "value") ? descriptor.value : undefined;
}

function record(value) {
  if (value === null || typeof value !== "object" || Array.isArray(value) ||
      ![Object.prototype, null].includes(Object.getPrototypeOf(value))) return null;
  const keys = Reflect.ownKeys(value);
  if (keys.length !== FIELDS.length ||
      !keys.every(key => typeof key === "string" && FIELDS.includes(key))) return null;
  const data = Object.create(null);
  for (const key of FIELDS) {
    const descriptor = Object.getOwnPropertyDescriptor(value, key);
    if (!descriptor || !Object.hasOwn(descriptor, "value")) return null;
    data[key] = descriptor.value;
  }
  return data;
}

function verifiedDownload(source, intent, downloadId, now, startedAtMs = null) {
  const data = record(source);
  if (!data || data.requestId !== intent.requestId ||
      data.downloadId !== downloadId ||
      data.selectionId !== intent.selectionId ||
      data.tabId !== intent.tabId || data.frameId !== intent.frameId ||
      data.verified !== true || data.permissionGranted !== true ||
      !["in_progress", "complete", "interrupted"].includes(data.state) ||
      !Number.isSafeInteger(data.startedAtMs) || data.startedAtMs < 0 ||
      data.startedAtMs > now ||
      (startedAtMs !== null && data.startedAtMs !== startedAtMs)) return null;
  return Object.freeze({
    state: data.state, startedAtMs: data.startedAtMs
  });
}

function outcome(status, requestId, downloadId, timeoutMs, cancelRequested = false) {
  return Object.freeze({
    status, requestId, downloadId, timeoutMs,
    cancelRequested,
    transferComplete: status === "completed",
    scanVerified: false, authorizesScan: false, authorizesOpen: false,
    automaticallyRetry: false
  });
}

/**
 * An opt-in watchdog for a browser download ALREADY started by a trusted
 * Scan This PDF integration. It tracks elapsed WALL-CLOCK time from the
 * attested download start, not from when a timer happens to be scheduled.
 *
 * readVerifiedActiveDownload(reference) MUST be a synchronous, own,
 * network-free coordinator method returning the exact FIELDS above. The
 * coordinator must authenticate browser download ID provenance, the selected
 * PDF, current access grant and start timestamp. Event IDs alone are not
 * sufficient proof to cancel a browser download.
 *
 * On expiry, block the attempt synchronously BEFORE calling downloads.cancel;
 * cancellation is best effort and can never authorize scanning/opening.
 * The caller must consult isBlocked before native handoff. Real integrations
 * must persist deadlines and recheck them on service-worker resume, because
 * a background worker may suspend JavaScript timers.
 */
export function createExplicitPdfDownloadTimeout({
  downloadsApi, coordinator, clock = Date.now,
  schedule = setTimeout, unschedule = clearTimeout
} = {}) {
  const attempted = new Set();
  const active = new Map();
  const results = new Map();
  let ended = false;

  function isBlocked(requestId) {
    if (ended || typeof requestId !== "string" || !ID.test(requestId)) return true;
    // Only a trusted completed transfer is non-blocked. This alone is NOT
    // proof of a safe PDF or permission to hand it to the native scanner.
    return results.get(requestId)?.status !== "completed";
  }

  function watch(request, downloadId, timeoutMs = EXPLICIT_PDF_DOWNLOAD_TIMEOUT_MS) {
    if (ended) return null;
    const intent = describeExplicitPdfScanRequest(request);
    if (!intent || !Number.isSafeInteger(downloadId) || downloadId < 0 ||
        !Number.isSafeInteger(timeoutMs) || timeoutMs < 1 ||
        timeoutMs > MAX_EXPLICIT_PDF_DOWNLOAD_TIMEOUT_MS ||
        attempted.has(intent.requestId) || attempted.size >= MAX_ATTEMPTS ||
        active.size >= MAX_ACTIVE || typeof clock !== "function" ||
        typeof schedule !== "function" || typeof unschedule !== "function" ||
        own(coordinator, "downloadTimeoutReady") !== true) return null;
    const read = own(coordinator, "readVerifiedActiveDownload");
    const cancel = own(downloadsApi, "cancel");
    if (typeof read !== "function" || typeof cancel !== "function") return null;

    const reference = Object.freeze({
      requestId: intent.requestId, selectionId: intent.selectionId,
      tabId: intent.tabId, frameId: intent.frameId, downloadId
    });
    let initial;
    try {
      const now = clock();
      if (!Number.isSafeInteger(now) || now < 0) return null;
      initial = verifiedDownload(read.call(coordinator, reference),
        intent, downloadId, now);
      if (!initial || initial.state !== "in_progress") return null;
    } catch { return null; }

    // The request cannot be watched or submitted twice even if setup fails.
    attempted.add(intent.requestId);
    const deadline = initial.startedAtMs + timeoutMs;
    if (!Number.isSafeInteger(deadline)) {
      results.set(intent.requestId, outcome("unavailable",
        intent.requestId, downloadId, timeoutMs));
      return null;
    }
    let current = outcome("monitoring", intent.requestId, downloadId, timeoutMs);
    let timer = null;
    let unsubscribe = null;
    let settled = false;
    let resolveDone;
    const done = new Promise(resolve => { resolveDone = resolve; });

    function stop(status, requestCancel = false) {
      if (settled) return;
      settled = true;
      current = outcome(status, intent.requestId, downloadId, timeoutMs, requestCancel);
      results.set(intent.requestId, current);
      active.delete(intent.requestId);
      if (timer !== null) {
        try { unschedule(timer); } catch { /* terminal veto remains latched */ }
        timer = null;
      }
      try { unsubscribe?.(); } catch { /* callbacks are already disabled */ }
      resolveDone(current);
      if (requestCancel) {
        // Mark the attempt blocked BEFORE asking the browser to cancel.
        // A rejected/hung browser cancellation cannot reset the deadline.
        try { Promise.resolve(cancel.call(downloadsApi, downloadId)).catch(() => {}); }
        catch { /* a failed cancellation is never a clean scan */ }
      }
    }

    function reread() {
      try {
        const now = clock();
        if (!Number.isSafeInteger(now) || now < initial.startedAtMs) return null;
        const source = verifiedDownload(read.call(coordinator, reference),
          intent, downloadId, now, initial.startedAtMs);
        return source ? Object.freeze({ now, state: source.state }) : null;
      } catch { return null; }
    }

    function checkDeadline() {
      if (settled) return current;
      if (timer !== null) {
        try { unschedule(timer); } catch { /* timer callbacks recheck settled state */ }
        timer = null;
      }
      const evidence = reread();
      if (!evidence) {
        stop("unavailable");
      } else if (evidence.now >= deadline) {
        stop("timed-out", evidence.state === "in_progress");
      } else if (evidence.state !== "in_progress") {
        // Do not infer safe completion from a missing/late browser event.
        stop("unavailable");
      } else {
        try {
          timer = schedule(() => {
            timer = null;
            checkDeadline();
          }, Math.max(1, deadline - evidence.now));
        } catch { stop("unavailable"); }
      }
      return current;
    }

    function onEvent(event) {
      if (settled || event.id !== downloadId) return;
      if (event.kind === "erased") {
        stop("unavailable");
        return;
      }
      if (event.kind !== "changed" ||
          (event.state !== "complete" && event.state !== "interrupted")) return;
      const evidence = reread();
      if (!evidence) stop("unavailable");
      else if (evidence.now >= deadline) {
        stop("timed-out", evidence.state === "in_progress");
      } else if (evidence.state === event.state) {
        stop(event.state === "complete" ? "completed" : "interrupted");
      } else stop("unavailable");
    }

    function dispose() {
      if (!settled) {
        const evidence = reread();
        stop("disposed", evidence?.state === "in_progress");
      }
      return current;
    }

    const session = Object.freeze({
      state: () => current, done,
      checkDeadline, dispose
    });
    active.set(intent.requestId, session);
    try {
      unsubscribe = subscribeToDownloadEvents(downloadsApi, onEvent, {
        onError: () => stop("unavailable")
      });
      checkDeadline();
    } catch { stop("unavailable"); }
    return session;
  }

  function dispose() {
    if (ended) return;
    ended = true;
    for (const session of [...active.values()]) session.dispose();
    active.clear();
  }

  return Object.freeze({ watch, isBlocked, dispose });
}
