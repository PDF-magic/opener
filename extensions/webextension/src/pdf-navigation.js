import { detectPdfCandidate } from "./pdf-detection.js";

// Browser-neutral event classifier for future webNavigation.onCommitted or
// equivalent trusted browser event dispatch. This module does not subscribe to
// events, inspect content, request permission, scan or open anything.
const NO_CANDIDATE = Object.freeze({
  isPdfCandidate: false, evidence: "none", authorizesOpen: false
});

function ownData(record, key) {
  const descriptor = Object.getOwnPropertyDescriptor(record, key);
  return descriptor && Object.hasOwn(descriptor, "value") ?
    descriptor.value : undefined;
}

/**
 * Identify a PDF-suffixed URL in a *browser-provided*, top-frame navigation
 * event. Metadata and its source must be trusted by the future caller; this
 * helper cannot authenticate a browser event or authorize any subsequent act.
 *
 * @param {{url: string, tabId: number, frameId: number}} details
 * @returns {{isPdfCandidate: boolean, evidence: string, authorizesOpen: false}}
 */
export function detectPdfNavigation(details) {
  try {
    if (details === null || typeof details !== "object" ||
        Array.isArray(details) ||
        ![Object.prototype, null].includes(Object.getPrototypeOf(details))) {
      return NO_CANDIDATE;
    }

    // A top-frame navigation in a real tab is distinct from a PDF embedded
    // in a subframe, discarded tab, preload or untrusted arbitrary URL string.
    const frameId = ownData(details, "frameId");
    const tabId = ownData(details, "tabId");
    const url = ownData(details, "url");
    if (frameId !== 0 || !Number.isSafeInteger(tabId) || tabId < 0 ||
        typeof url !== "string") return NO_CANDIDATE;

    // Reuse the single validated URL-path classifier. Do not treat arbitrary
    // event MIME/filename claims or query/fragment text as PDF navigation.
    const result = detectPdfCandidate({ url });
    return result.isPdfCandidate && result.evidence === "url-path" ?
      result : NO_CANDIDATE;
  } catch {
    // Malformed browser metadata or proxy traps must not throw, log secrets
    // or turn a suspicious URL into an authorization to scan/open.
    return NO_CANDIDATE;
  }
}
