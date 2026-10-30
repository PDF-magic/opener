import { describeExplicitPdfScanRequest } from "./explicit-pdf-scan-request.js";
import { submitCompletedPdfDownloadToNative } from "./download-native-submit.js";

// A trusted explicit selection must match the completed browser download
// before the existing reviewed native scanner submission adapter is invoked.
const unavailable = Object.freeze({
  status: "unavailable", scanSubmitted: false,
  scanVerified: false, authorizesOpen: false
});
const submitted = Object.freeze({
  status: "submitted", scanSubmitted: true,
  scanVerified: false, authorizesOpen: false
});
const ASSOCIATION_FIELDS = Object.freeze([
  "requestId", "source", "tabId", "frameId", "selectionId",
  "downloadId", "verified"
]);
const ACQUISITION_FIELDS = Object.freeze([
  "status", "downloadId", "downloadStarted", "scanVerified",
  "authorizesScan", "authorizesOpen"
]);
const MAX_REQUESTS = 128;

function own(value, key) {
  if (value === null || (typeof value !== "object" && typeof value !== "function")) {
    return undefined;
  }
  const desc = Object.getOwnPropertyDescriptor(value, key);
  return desc && Object.hasOwn(desc, "value") ? desc.value : undefined;
}

function record(value, fields) {
  if (value === null || typeof value !== "object" || Array.isArray(value) ||
      ![Object.prototype, null].includes(Object.getPrototypeOf(value))) return false;
  const keys = Reflect.ownKeys(value);
  return keys.length === fields.length &&
    keys.every(key => typeof key === "string" && fields.includes(key)) &&
    fields.every(key => {
      const desc = Object.getOwnPropertyDescriptor(value, key);
      return desc && Object.hasOwn(desc, "value");
    });
}

function acquiredId(acquisition, completion) {
  if (!record(acquisition, ACQUISITION_FIELDS) ||
      own(acquisition, "status") !== "download-started" ||
      own(acquisition, "downloadStarted") !== true ||
      own(acquisition, "scanVerified") !== false ||
      own(acquisition, "authorizesScan") !== false ||
      own(acquisition, "authorizesOpen") !== false) return null;
  const id = own(acquisition, "downloadId");
  if (!Number.isSafeInteger(id) || id < 0 ||
      !record(completion, ["kind", "id"]) ||
      own(completion, "kind") !== "completed" ||
      own(completion, "id") !== id) return null;
  return id;
}

function association(value, intent, id) {
  return record(value, ASSOCIATION_FIELDS) &&
    own(value, "requestId") === intent.requestId &&
    own(value, "source") === intent.source &&
    own(value, "tabId") === intent.tabId &&
    own(value, "frameId") === intent.frameId &&
    own(value, "selectionId") === intent.selectionId &&
    own(value, "downloadId") === id &&
    own(value, "verified") === true;
}

/**
 * Submit a completed PDF through the existing exact-ID, warning-aware native
 * scan gate, not directly to the transport-only native host.
 *
 * A separately authenticated integration must supply independent proof that
 * the explicit request actually produced the selected completed download,
 * a persistent session-owned scanGate and a real trusted native coordinator.
 * These JavaScript flags and association records are not themselves proof of
 * browser authenticity, local file identity or scanner readiness.
 */
export function createExplicitPdfNativeScanHandoff({
  downloadsApi, permissionsApi, coordinator, scanGate
} = {}) {
  const attempted = new Set();
  let disposed = false;
  let generation = 0;

  async function submitAcquiredPdf({ request, acquisition, completion } = {}) {
    if (disposed) return unavailable;
    try {
      const intent = describeExplicitPdfScanRequest(request);
      const id = acquiredId(acquisition, completion);
      if (!intent || id === null ||
          attempted.has(intent.requestId) || attempted.size >= MAX_REQUESTS ||
          own(coordinator, "explicitPdfScanReady") !== true ||
          own(coordinator, "nativeScannerReady") !== true) return unavailable;
      const read = own(coordinator, "readVerifiedAcquiredPdf");
      const send = own(coordinator, "submitCompletedPdfDownload");
      if (typeof read !== "function" || typeof send !== "function" ||
          typeof own(scanGate, "submitOnce") !== "function") return unavailable;

      attempted.add(intent.requestId);
      const version = generation;
      const reference = Object.freeze({
        requestId: intent.requestId, source: intent.source,
        tabId: intent.tabId, frameId: intent.frameId,
        selectionId: intent.selectionId, downloadId: id
      });
      const current = () => !disposed && version === generation &&
        own(coordinator, "explicitPdfScanReady") === true &&
        own(coordinator, "nativeScannerReady") === true &&
        own(coordinator, "readVerifiedAcquiredPdf") === read &&
        own(coordinator, "submitCompletedPdfDownload") === send &&
        association(read.call(coordinator, reference), intent, id);
      if (!current()) return unavailable;

      // Browser completion and an acquisition acknowledgement are untrusted.
      // The existing adapter rechecks downloads permission, transfer bytes,
      // exact path, PDF type, browser malware warnings and one-shot scan IDs.
      const scoped = Object.freeze({
        nativeScannerReady: true,
        submitCompletedPdfDownload(candidate) {
          if (!current() || own(candidate, "id") !== id) {
            return Promise.resolve({ accepted: false });
          }
          return send.call(coordinator, candidate);
        }
      });
      const result = await submitCompletedPdfDownloadToNative({
        downloadsApi, permissionsApi, completion,
        coordinator: scoped, scanGate
      });
      if (!current() || own(result, "status") !== "submitted" ||
          own(result, "id") !== id ||
          own(result, "scanSubmitted") !== true) return unavailable;
      return submitted;
    } catch {
      // Native/browser error strings may contain sensitive URLs and paths.
      return unavailable;
    }
  }

  function dispose() {
    disposed = true;
    generation++;
    attempted.clear();
  }

  return Object.freeze({ submitAcquiredPdf, dispose });
}
