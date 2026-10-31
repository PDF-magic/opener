import {
  MAX_EXPLICIT_PDF_DOWNLOAD_BYTES,
  MAX_EXPLICIT_PDF_DOWNLOAD_CHUNK_BYTES
} from "./explicit-pdf-download-size.js";
import { getPdfInterceptionPointAssessment } from "./pdf-interception-point-assessment.js";

// A design-only contract for passing a captured PDF to the *existing*
// independently trusted native scanning boundary. Nothing in this module
// acquires bytes, starts a browser listener, sends native messages, or opens PDFs.
export const INTERCEPTED_PDF_SCANNER_TRANSFER_VERSION = 1;
export const INTERCEPTED_PDF_SCANNER_TRANSFER_FIELDS = Object.freeze([
  "version", "browserId", "source", "requestId", "captureId",
  "tabId", "frameId", "maxBytes"
]);

const ID = /^[A-Za-z0-9_-]{1,80}$/u;
const RESPONSE_STEPS = Object.freeze([
  "hold-original-response-with-effective-browser-grants",
  "copy-all-bytes-with-hard-size-and-time-bounds-to-native-private-quarantine",
  "authenticate-request-and-final-response-and-revalidate-staged-file",
  "run-native-fresh-signature-scan-and-quarantine-policy",
  "release-only-after-independent-clean-verdict"
]);
const DOWNLOAD_STEPS = Object.freeze([
  "verify-current-completed-browser-download-and-native-warning-state",
  "resolve-stable-local-copy-through-trusted-native-coordinator",
  "revalidate-file-identity-and-run-native-fresh-signature-scan",
  "apply-native-quarantine-and-scan-before-open-policy"
]);

function own(value, key) {
  const descriptor = Object.getOwnPropertyDescriptor(value, key);
  return descriptor && Object.hasOwn(descriptor, "value") ?
    descriptor.value : undefined;
}

function fields(value) {
  if (value === null || typeof value !== "object" || Array.isArray(value) ||
      ![Object.prototype, null].includes(Object.getPrototypeOf(value))) {
    return false;
  }
  const keys = Reflect.ownKeys(value);
  return keys.length === INTERCEPTED_PDF_SCANNER_TRANSFER_FIELDS.length &&
    keys.every(key => typeof key === "string" &&
      INTERCEPTED_PDF_SCANNER_TRANSFER_FIELDS.includes(key) &&
      Object.hasOwn(Object.getOwnPropertyDescriptor(value, key), "value"));
}

/**
 * Describe the only two candidate transfer routes without executing either:
 *
 * - Firefox's conditionally available response filter -> bounded native-owned
 *   quarantine spool -> independent scanner. The original response must stay
 *   held until a verified clean verdict; no such live bridge exists today.
 * - A verified completed browser download -> existing trusted download-native
 *   scanner handoff. Download observation is *not* interception or a pre-render
 *   gate, including in Firefox.
 *
 * Callers must separately authenticate the browser event, final response,
 * current permissions/opt-in, exact captured bytes, native coordinator and
 * file identity. This metadata and its booleans NEVER constitute such proof.
 * A valid plan cannot submit a scan, release response bytes, or authorize open.
 */
export function describeInterceptedPdfScannerTransfer(input) {
  try {
    if (!fields(input)) return null;
    const browserId = own(input, "browserId");
    const source = own(input, "source");
    const requestId = own(input, "requestId");
    const captureId = own(input, "captureId");
    const tabId = own(input, "tabId");
    const frameId = own(input, "frameId");
    const maxBytes = own(input, "maxBytes");

    if (own(input, "version") !== INTERCEPTED_PDF_SCANNER_TRANSFER_VERSION ||
        typeof browserId !== "string" ||
        !["response-stream", "completed-download"].includes(source) ||
        typeof requestId !== "string" || !ID.test(requestId) ||
        typeof captureId !== "string" || !ID.test(captureId) ||
        captureId === requestId ||
        !Number.isSafeInteger(tabId) || tabId < 0 ||
        frameId !== 0 ||
        !Number.isSafeInteger(maxBytes) || maxBytes < 1 ||
        maxBytes > MAX_EXPLICIT_PDF_DOWNLOAD_BYTES) return null;

    const point = getPdfInterceptionPointAssessment(browserId);
    if (point.browserId === null) return null;

    const response = source === "response-stream";
    if (response ?
      point.responseBodyStreamPoint !==
        "firefox-response-filter-with-additional-grants" :
      point.downloadEventPoint !== "observation-after-download-start-only") {
      return null;
    }

    return Object.freeze({
      version: INTERCEPTED_PDF_SCANNER_TRANSFER_VERSION,
      browserId, source, requestId, captureId, tabId, frameId,
      maxBytes,
      maxChunkBytes: Math.min(maxBytes, MAX_EXPLICIT_PDF_DOWNLOAD_CHUNK_BYTES),
      route: response ? "native-private-quarantine-spool" :
        "existing-verified-completed-download-handoff",
      steps: response ? RESPONSE_STEPS : DOWNLOAD_STEPS,
      status: response ? "conditional-response-stream-design" :
        "post-download-scan-only",
      requiresTrustedNativeCoordinator: true,
      requiresCompletePdfBytes: true,
      requiresExactRequestAndFileIdentity: true,
      requiresEffectiveRevocablePermissions: true,
      requiresNativeQuarantineAndCleanVerdict: true,
      requiresOriginalResponseHold: response,
      preRenderGuaranteed: false,
      scannerTransferReady: false,
      automaticInterceptionEnabled: false,
      scanVerified: false,
      authorizesScan: false,
      authorizesOpen: false
    });
  } catch {
    // Hostile properties and Proxies must never leak URLs, paths or error text.
    return null;
  }
}
