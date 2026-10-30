import { describeExplicitPdfScanRequest } from "./explicit-pdf-scan-request.js";
import { subscribeToPermissionRevocations } from "./permission-revocations.js";

// A browser download is an untrusted transfer, not a verified PDF or scan.
// No browser globals, listeners, permissions, network or native work on import.
const UNAVAILABLE = Object.freeze({
  status: "unavailable", downloadStarted: false,
  scanVerified: false, authorizesScan: false, authorizesOpen: false
});
const MAX_REQUESTS = 128;

function own(record, key) {
  if (record === null || (typeof record !== "object" &&
      typeof record !== "function")) return undefined;
  const descriptor = Object.getOwnPropertyDescriptor(record, key);
  return descriptor && Object.hasOwn(descriptor, "value") ?
    descriptor.value : undefined;
}

function method(record, key) {
  const value = own(record, key);
  return typeof value === "function" ? value : null;
}

function verifiedSource(value, selectionId) {
  if (value === null || typeof value !== "object" || Array.isArray(value) ||
      ![Object.prototype, null].includes(Object.getPrototypeOf(value)) ||
      Reflect.ownKeys(value).length !== 3 ||
      own(value, "selectionId") !== selectionId ||
      own(value, "verified") !== true) return null;
  const url = own(value, "url");
  if (typeof url !== "string" || !url.length || url.length > 8192 ||
      /[\u0000-\u0020\u007f]/u.test(url) ||
      /%(?![0-9a-f]{2})/iu.test(url)) return null;
  const parsed = new URL(url);
  if (!["http:", "https:"].includes(parsed.protocol) || !parsed.hostname ||
      parsed.username || parsed.password) return null;
  // Reject ambiguous encoded path separators and controls. A final response
  // MUST be independently verified after redirects and transfer completion.
  if (/[\\/\u0000-\u001f\u007f]/u.test(
    decodeURIComponent(parsed.pathname.split("/").at(-1))
  )) return null;
  return url;
}

/**
 * A dormant acquisition adapter for trusted, explicitly clicked Scan This PDF
 * requests. The coordinator MUST independently attest the current PDF source,
 * a reuse-first "not present" decision, download auto-open safety and native
 * scanner readiness. Assertions on an arbitrary JS object are NOT proof.
 *
 * This adapter starts a browser-supported downloads.download() transfer only
 * with the existing optional downloads grant. It never calls downloads.open,
 * accepts page-supplied URLs, bypasses browser warnings, or sends a scan.
 */
export function createExplicitPdfDownloadAcquisition(
  { downloadsApi, permissionsApi, coordinator } = {}
) {
  const reserved = new Set();

  function ready(selectionId) {
    return own(coordinator, "sourceAcquisitionReady") === true &&
      own(coordinator, "sourceAcquisitionNeeded") === true &&
      own(coordinator, "browserDownloadSafetyReady") === true &&
      own(coordinator, "nativeScannerReady") === true &&
      method(coordinator, "resolveVerifiedPdfSource") !== null &&
      method(coordinator, "readCurrentSelectionId") !== null &&
      method(coordinator, "readCurrentSelectionId").call(coordinator) === selectionId;
  }

  async function acquire(request) {
    let revocations = null;
    let startedId = null;
    try {
      const intent = describeExplicitPdfScanRequest(request);
      const download = method(downloadsApi, "download");
      const cancel = method(downloadsApi, "cancel");
      const contains = method(permissionsApi, "contains");
      if (!intent || !download || !cancel || !contains ||
          !ready(intent.selectionId) || reserved.has(intent.requestId) ||
          reserved.size >= MAX_REQUESTS) return UNAVAILABLE;

      // One attempt per ID, even when the permission or browser call fails.
      // Prevent concurrent gestures from starting duplicate acquisitions.
      reserved.add(intent.requestId);
      revocations = subscribeToPermissionRevocations(permissionsApi, () => {});
      const revoked = () => revocations.isRevoked("downloads") ||
        revocations.isRevoked("siteAccess");

      const sourcePromise = method(coordinator, "resolveVerifiedPdfSource")
        .call(coordinator, Object.freeze({
          selectionId: intent.selectionId, tabId: intent.tabId,
          frameId: intent.frameId
        }));
      if (!sourcePromise || typeof sourcePromise.then !== "function") return UNAVAILABLE;
      const source = await sourcePromise;
      const url = verifiedSource(source, intent.selectionId);
      if (!url || revoked() || !ready(intent.selectionId)) return UNAVAILABLE;

      // The browser's optional downloads permission must already be granted.
      // Never request permission after transient user activation expires.
      const permission = contains.call(permissionsApi, { permissions: ["downloads"] });
      if (!permission || typeof permission.then !== "function" ||
          await permission !== true || revoked() ||
          !ready(intent.selectionId)) return UNAVAILABLE;

      // saveAs asks the user to choose a destination. Never silently
      // overwrite, auto-accept security warnings, or open the resulting file.
      const pending = download.call(downloadsApi, Object.freeze({
        url, saveAs: true, conflictAction: "uniquify"
      }));
      if (!pending || typeof pending.then !== "function") return UNAVAILABLE;
      const id = await pending;
      if (!Number.isSafeInteger(id) || id < 0) return UNAVAILABLE;
      startedId = id;

      if (revoked() || !ready(intent.selectionId)) {
        // Cancellation is best effort: browser downloads/opening policy must
        // independently remain fail-closed even if this arrives too late.
        try { await cancel.call(downloadsApi, id); } catch {}
        return UNAVAILABLE;
      }
      return Object.freeze({
        status: "download-started", downloadId: id, downloadStarted: true,
        scanVerified: false, authorizesScan: false, authorizesOpen: false
      });
    } catch {
      // Browser errors and source URLs may contain secrets. Never disclose.
      if (startedId !== null) {
        try { await method(downloadsApi, "cancel")?.call(downloadsApi, startedId); }
        catch {}
      }
      return UNAVAILABLE;
    } finally {
      try { revocations?.unsubscribe(); } catch {}
    }
  }

  return Object.freeze({ acquire });
}
