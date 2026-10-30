// Shared, opt-in WebExtensions update event handling (opener-0581).
// Observes version changes only. Never changes stored preferences, requests
// browser permissions, reloads the extension or invokes a PDF scan/open path.

const versionPattern = /^(?:0|[1-9]\d{0,4})(?:\.(?:0|[1-9]\d{0,4})){2,3}$/;

function isRecord(value) {
  if (value === null || typeof value !== "object" || Array.isArray(value)) return false;
  const prototype = Object.getPrototypeOf(value);
  return prototype === Object.prototype || prototype === null;
}

function dataField(record, field) {
  if (!isRecord(record)) return undefined;
  const descriptor = Object.getOwnPropertyDescriptor(record, field);
  return descriptor && Object.hasOwn(descriptor, "value") ? descriptor.value : undefined;
}

function validVersion(value) {
  return typeof value === "string" && value.length <= 64 &&
    versionPattern.test(value) &&
    value.split(".").every((part) => Number(part) <= 65535);
}

/**
 * Reduce a browser runtime.onInstalled update notification to immutable,
 * version-only metadata. Install, browser update and other reasons are not
 * extension updates. Untrusted detail fields are never forwarded.
 */
export function normalizeExtensionUpdate(details, currentVersion) {
  if (dataField(details, "reason") !== "update") return null;
  const previousVersion = dataField(details, "previousVersion");
  if (!validVersion(previousVersion) || !validVersion(currentVersion) ||
      previousVersion === currentVersion) return null;
  return Object.freeze({
    kind: "extension-update",
    previousVersion,
    currentVersion
  });
}

/**
 * Explicitly observe actual extension updates using a supplied WebExtensions
 * runtime. The returned function detaches the listener. The caller decides
 * whether an update needs UI or a separately reviewed settings migration.
 *
 * No global browser/chrome API is accessed at import time, and this handler
 * never performs migrations, clears data or modifies user preferences.
 */
export function subscribeToExtensionUpdates(runtime, onUpdate, { onError } = {}) {
  if (typeof onUpdate !== "function" ||
      (onError !== undefined && typeof onError !== "function") ||
      typeof runtime?.onInstalled?.addListener !== "function" ||
      typeof runtime?.onInstalled?.removeListener !== "function" ||
      typeof runtime?.getManifest !== "function") {
    throw new TypeError("A complete extension update event source and callback are required");
  }

  let active = false;
  let lastUpdateKey = null;
  const reportError = (error) => {
    try { onError?.(error); } catch { /* error hooks cannot interrupt dispatch */ }
  };
  const listener = (details) => {
    if (!active || dataField(details, "reason") !== "update") return;

    let currentVersion;
    try {
      currentVersion = dataField(runtime.getManifest(), "version");
    } catch {
      // A failed manifest lookup must never cause an update to be treated as
      // verified or cause any state mutation.
      reportError(new Error("Extension update version unavailable"));
      return;
    }

    const event = normalizeExtensionUpdate(details, currentVersion);
    if (event === null) return;

    const key = event.previousVersion + ">" + event.currentVersion;
    if (lastUpdateKey === key) return;
    lastUpdateKey = key; // Also guards against reentrant duplicate delivery.
    try { onUpdate(event); } catch (error) { reportError(error); }
  };

  try {
    runtime.onInstalled.addListener(listener);
    active = true;
  } catch (error) {
    // Some browser implementations can throw after partial registration.
    try { runtime.onInstalled.removeListener(listener); } catch { /* fail closed */ }
    throw error;
  }

  return function unsubscribe() {
    if (!active) return;
    active = false;
    try { runtime.onInstalled.removeListener(listener); } catch {
      // Even if the browser fails to detach, the inactive callback is inert.
    }
  };
}
