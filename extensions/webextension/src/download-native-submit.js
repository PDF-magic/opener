import { subscribeToDownloadEvents } from "./download-monitoring.js";
import { subscribeToPermissionRevocations } from "./permission-revocations.js";
import { preflightCompletedDownloadForScan } from "./download-scan-preflight.js";
import { retrieveCompletedDownloadLocalPath } from "./download-local-path.js";
import { retrieveCompletedDownloadMime } from "./download-mime.js";
import { detectCompletedDownloadPdfMime } from "./download-pdf-mime.js";
import { detectCompletedPdfFilename } from "./download-pdf-filename.js";

// A browser event cannot authenticate a native host or authorize a scan.
// Only a separately authenticated native scanner coordinator may receive a
// proposed local path; the native side must independently revalidate it.
const unavailable = Object.freeze({
  status: "unavailable", scanSubmitted: false,
  scanVerified: false, authorizesOpen: false
});

function own(value, key) {
  if (value === null || typeof value !== "object") return undefined;
  const descriptor = Object.getOwnPropertyDescriptor(value, key);
  return descriptor && Object.hasOwn(descriptor, "value")
    ? descriptor.value : undefined;
}

function completedId(value) {
  if (value === null || typeof value !== "object" || Array.isArray(value) ||
      ![Object.prototype, null].includes(Object.getPrototypeOf(value)) ||
      Reflect.ownKeys(value).length !== 2 ||
      own(value, "kind") !== "completed") return null;
  const id = own(value, "id");
  return Number.isSafeInteger(id) && id >= 0 ? id : null;
}

function pdfCandidate(id, path, mimeRecord) {
  const name = detectCompletedPdfFilename({ id, filename: path });
  if (name === null) return false;
  if (mimeRecord === null) return name.isPdfFilename;
  const mime = detectCompletedDownloadPdfMime(mimeRecord);
  if (mime === null || mime.id !== id) return false;
  if (mime.isPdfMime) return true;
  // An explicit non-PDF Content-Type must veto a misleading .pdf suffix.
  const declaration = mimeRecord.mime.split(";", 1)[0].trim().toLowerCase();
  return (declaration === "application/octet-stream" ||
    declaration === "binary/octet-stream") && name.isPdfFilename;
}

/**
 * One-shot, opt-in handoff of a verified completed PDF *candidate* to an
 * injected trusted native scanner coordinator. This does not connect to the
 * current transport-only native host, activate background monitoring, or
 * interpret a coordinator acknowledgement as a scanner verdict.
 *
 * A future trusted integration must independently authenticate the native
 * session, provide a session-owned createCompletedDownloadScanRequestGate()
 * instance, and expose nativeScannerReady only after verifying its scanner
 * coordinator. The flag itself is NOT a security credential or attestation.
 * The receiving native coordinator must independently validate path identity,
 * file stability, signature freshness, full scanning and quarantine.
 */
export async function submitCompletedPdfDownloadToNative({
  downloadsApi, permissionsApi, completion, coordinator, scanGate
} = {}) {
  let stopEvents = null;
  let revocations = null;
  try {
    const id = completedId(completion);
    const send = own(coordinator, "submitCompletedPdfDownload");
    const reserve = own(scanGate, "submitOnce");
    if (id === null || own(coordinator, "nativeScannerReady") !== true ||
        typeof send !== "function" || typeof reserve !== "function") {
      return unavailable;
    }

    // Watch revocations and ID reuse throughout all asynchronous browser
    // rechecks, rather than trusting an earlier completion notification.
    revocations = subscribeToPermissionRevocations(permissionsApi, () => {});
    let stale = false;
    stopEvents = subscribeToDownloadEvents(downloadsApi, (event) => {
      if (event.id !== id) return;
      if (event.kind !== "changed" || event.filename !== undefined ||
          (event.state !== undefined && event.state !== "complete") ||
          event.error !== undefined) stale = true;
    });
    const invalidated = () => stale || revocations.isRevoked("downloads");

    const before = await preflightCompletedDownloadForScan(
      downloadsApi, permissionsApi, completion
    );
    if (before === null || before.id !== id || invalidated()) return unavailable;

    const [path, mime] = await Promise.all([
      retrieveCompletedDownloadLocalPath(downloadsApi, permissionsApi, completion),
      retrieveCompletedDownloadMime(downloadsApi, permissionsApi, completion)
    ]);
    if (!path || path.id !== id || invalidated() ||
        !pdfCandidate(id, path.localPath, mime)) return unavailable;

    // Revalidate after the metadata lookups. A browser ID, MIME or path can
    // become stale during these awaits, and native identity must still be
    // checked AGAIN by the trusted scanner, never by browser assertions.
    const after = await preflightCompletedDownloadForScan(
      downloadsApi, permissionsApi, completion
    );
    const current = await retrieveCompletedDownloadLocalPath(
      downloadsApi, permissionsApi, completion
    );
    if (after === null || after.id !== id ||
        current === null || current.id !== id ||
        current.localPath !== path.localPath || invalidated() ||
        own(coordinator, "nativeScannerReady") !== true) return unavailable;

    // Only explicitly injected, independently verified native coordination
    // receives the untrusted browser path. No raw native messaging payload is
    // constructed; the existing transport-only host rejects file paths.
    const request = Object.freeze({ id, localPath: current.localPath });
    // The session-owned gate reserves this browser ID before calling native
    // coordination; repeated completion events cannot start duplicate scans.
    const result = await reserve.call(scanGate, after, () => {
      const pending = send.call(coordinator, request);
      return pending && typeof pending.then === "function"
        ? pending : Promise.resolve({ accepted: false });
    });
    if (invalidated() || own(result, "status") !== "request-submitted") {
      return unavailable;
    }
    return Object.freeze({
      status: "submitted", id, scanSubmitted: true,
      scanVerified: false, authorizesOpen: false
    });
  } catch {
    // Never leak download paths, native errors, or privileged browser data.
    return unavailable;
  } finally {
    try { stopEvents?.(); } catch { /* never undo invalidation */ }
    try { revocations?.unsubscribe(); } catch { /* deny on cleanup error */ }
  }
}
