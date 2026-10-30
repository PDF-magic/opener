// Present a clean result only when a separately authenticated native scanner
// coordinator has delivered a correlated, completed, verified scan result.
// The installed WebExtension has no such coordinator and stays inactive.
const IDENTIFIER = /^[A-Za-z0-9_-]{1,80}$/u;
const UNKNOWN = "No verified clean scan result is available.";
const CLEAN = "Scan complete: required checks found no threats. Opening still requires separate approval.";

function own(value, key) {
  if (value === null || typeof value !== "object") return undefined;
  const descriptor = Object.getOwnPropertyDescriptor(value, key);
  return descriptor && Object.hasOwn(descriptor, "value") ? descriptor.value : undefined;
}

function hasOnly(value, keys) {
  if (value === null || typeof value !== "object" || Array.isArray(value) ||
      ![Object.prototype, null].includes(Object.getPrototypeOf(value))) return false;
  const actual = Reflect.ownKeys(value);
  return actual.length === keys.length && keys.every(key => actual.includes(key));
}

function verifiedCleanResult(message, requestId, scanRequestId) {
  if (typeof requestId !== "string" || !IDENTIFIER.test(requestId) ||
      typeof scanRequestId !== "string" || !IDENTIFIER.test(scanRequestId) ||
      !hasOnly(message, ["version", "kind", "topic", "requestId", "payload"]) ||
      own(message, "version") !== 1 || own(message, "kind") !== "response" ||
      own(message, "topic") !== "scan.result" ||
      own(message, "requestId") !== requestId) return false;

  const payload = own(message, "payload");
  if (!hasOnly(payload, ["scanRequestId", "status", "result",
    "scanCompleted", "scanVerified", "authorizesOpen"]) ||
      own(payload, "scanRequestId") !== scanRequestId ||
      own(payload, "status") !== "complete" ||
      own(payload, "scanCompleted") !== true ||
      own(payload, "scanVerified") !== true ||
      own(payload, "authorizesOpen") !== false) return false;

  const result = own(payload, "result");
  return hasOnly(result, ["status"]) && own(result, "status") === "clean";
}

/**
 * Display a verified clean download scan result in an injected, trusted UI
 * status element. This is a PRESENTATION adapter, not scan verification:
 * callers must independently authenticate the native scanner coordinator,
 * correlate the response to their owned scan request, and enforce its native
 * ClamAV, unchanged-file, quarantine and opening gates.
 *
 * The current transport-only native host always reports unavailable; its
 * reply and any download submission acknowledgment cannot display "clean".
 * On every invalid or stale response clear any prior clean message instead
 * of leaving a misleading success visible.
 *
 * No raw paths, filenames, browser metadata or native diagnostics are rendered.
 * Only static strings are assigned via textContent, never HTML. Nothing is
 * installed in the inactive popup or browser background by importing this.
 */
export function displayVerifiedCleanDownloadScanResult(
  target, message, { requestId, scanRequestId } = {}
) {
  let clean = false;
  try {
    clean = verifiedCleanResult(message, requestId, scanRequestId);
  } catch {
    clean = false;
  }
  // A DOM-like status target is supplied by a separately trusted UI, not a
  // webpage. A missing/invalid target cannot make an unverified result clean.
  if (target === null || typeof target !== "object") return false;
  try {
    target.setAttribute("role", "status");
    target.setAttribute("aria-live", "polite");
    target.textContent = clean ? CLEAN : UNKNOWN;
    return clean;
  } catch {
    return false;
  }
}
