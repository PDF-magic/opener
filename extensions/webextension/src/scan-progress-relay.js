import { createMessage } from "./messaging.js";

// A passive extension-message relay for observations from a separately
// authenticated native scanner. The currently shipped host has no scan jobs.
const PHASES = ["queued", "starting", "scanning", "verifying"];
const validId = (id) => typeof id === "string" && id.length > 0 &&
  id.length <= 80 && /^[A-Za-z0-9_-]+$/u.test(id);
const noOp = () => {};

function own(value, key) {
  if (value === null || (typeof value !== "object" && typeof value !== "function")) {
    return undefined;
  }
  const descriptor = Object.getOwnPropertyDescriptor(value, key);
  return descriptor && Object.hasOwn(descriptor, "value") ? descriptor.value : undefined;
}

// Do not evaluate getters, trust inherited claims, accept scanner verdicts,
// or permit private paths and browser-supplied progress into the extension.
function progressPayload(event, requestId) {
  if (!event || typeof event !== "object" || Array.isArray(event) ||
      ![Object.prototype, null].includes(Object.getPrototypeOf(event))) return null;
  const keys = Reflect.ownKeys(event);
  if (keys.length !== 2 && keys.length !== 3) return null;
  if (!keys.includes("scanRequestId") || !keys.includes("stage") ||
      (keys.length === 3 && !keys.includes("percent"))) return null;

  const id = own(event, "scanRequestId");
  const stage = own(event, "stage");
  if (id !== requestId || !PHASES.includes(stage)) return null;
  const payload = { scanRequestId: requestId, stage };
  if (keys.length === 3) {
    const percent = own(event, "percent");
    // Progress cannot itself confirm completion, a clean verdict or opening.
    if (!Number.isInteger(percent) || percent < 0 || percent > 99) return null;
    payload.percent = percent;
  }
  return payload;
}

/**
 * Subscribe to real, correlated scan progress from an injected trusted native
 * coordinator and deliver path-free, versioned "scan.progress" extension events
 * to the supplied receiver. This helper does not connect to a native port or
 * start scans. It returns an idempotent unsubscriber; unavailable native
 * coordination returns a no-op without claiming that scanning began.
 *
 * The integrating application MUST independently authenticate the native
 * coordinator and bind this request ID to an accepted scan before calling.
 * nativeScannerReady is an additional availability check, NOT authentication.
 */
export function relayTrustedScanProgress(
  coordinator, scanRequestId, deliverToExtension, { onError } = {}
) {
  if (typeof deliverToExtension !== "function" ||
      (onError !== undefined && typeof onError !== "function")) {
    throw new TypeError("A progress delivery callback is required");
  }
  const reportError = () => {
    try { onError?.(new Error("Native scan progress delivery failed")); }
    catch { /* Never forward native error text or local paths. */ }
  };
  let active = false;
  let dispose = noOp;
  let lastPhase = -1;
  let lastPercent = -1;
  const stop = () => {
    if (!active) return;
    active = false;
    const unsubscribe = dispose;
    dispose = noOp;
    try { unsubscribe(); } catch { reportError(); }
  };
  try {
    const subscribe = own(coordinator, "subscribeScanProgress");
    if (!validId(scanRequestId) ||
        own(coordinator, "nativeScannerReady") !== true ||
        typeof subscribe !== "function") return noOp;

    active = true;
    const listener = (nativeEvent) => {
      if (!active) return;
      try {
        if (own(coordinator, "nativeScannerReady") !== true) {
          stop();
          return;
        }
        const payload = progressPayload(nativeEvent, scanRequestId);
        if (!payload) return;
        const phase = PHASES.indexOf(payload.stage);
        // Reject stale phase regressions and decreasing measured percentages.
        if (phase < lastPhase ||
            (payload.percent !== undefined && payload.percent < lastPercent)) return;
        const message = createMessage("event", "scan.progress", scanRequestId, payload);
        lastPhase = phase;
        if (payload.percent !== undefined) lastPercent = payload.percent;
        const detached = Object.freeze({
          ...message, payload: Object.freeze(message.payload)
        });
        const result = deliverToExtension(detached);
        if (result && typeof result.then === "function") {
          Promise.resolve(result).catch(reportError);
        }
      } catch {
        reportError();
      }
    };
    const unsubscribe = subscribe.call(coordinator, scanRequestId, listener);
    if (typeof unsubscribe !== "function") {
      active = false;
      return noOp;
    }
    if (!active) {
      // A synchronous update may revoke readiness before registration ends.
      try { unsubscribe(); } catch { reportError(); }
      return noOp;
    }
    dispose = unsubscribe;
    return stop;
  } catch {
    active = false;
    reportError();
    return noOp;
  }
}
