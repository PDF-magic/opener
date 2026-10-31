// Passive, text-only original URL display for a future extension-owned holding screen.
export const UNKNOWN_HOLDING_ORIGINAL_URL = "Original PDF URL unavailable.";
const ID = /^[A-Za-z0-9_-]{1,80}$/u;
const UNAVAILABLE = Object.freeze({
  status: "unavailable", displayed: false, authorizesScan: false, authorizesOpen: false
});
const DISPLAYED = Object.freeze({
  status: "displayed", displayed: true, authorizesScan: false, authorizesOpen: false
});

function own(record, key) {
  if (!record || typeof record !== "object") return undefined;
  const field = Object.getOwnPropertyDescriptor(record, key);
  return field && Object.hasOwn(field, "value") ? field.value : undefined;
}

function validateOriginal(record, holdingId) {
  if (!record || typeof record !== "object" || Array.isArray(record) ||
      ![Object.prototype, null].includes(Object.getPrototypeOf(record))) return null;
  const keys = Reflect.ownKeys(record);
  if (keys.length !== 2 || !keys.includes("holdingId") ||
      !keys.includes("originalUrl") || own(record, "holdingId") !== holdingId) return null;
  const url = own(record, "originalUrl");
  if (typeof url !== "string" || !url || url.length > 8192 ||
      /[\u0000-\u0020\u007f]/u.test(url)) return null;
  const parsed = new URL(url);
  if (!["http:", "https:"].includes(parsed.protocol) || !parsed.hostname ||
      parsed.username || parsed.password) return null;
  // Preserve the ORIGINAL captured string, never URL.href, a redirect or tab URL.
  return url;
}

function paint(target, url = null) {
  target.textContent = url ?? UNKNOWN_HOLDING_ORIGINAL_URL;
  target.setAttribute("role", "status");
  target.setAttribute("aria-live", "polite");
}

/**
 * The caller must supply an extension-owned element and an authenticated,
 * permission-verified coordinator which owns the current held navigation.
 * A ready flag is not itself proof of trust or a PDF scan verdict.
 * Does not activate interception, issue scanner commands or authorize opening.
 */
export function createHoldingScreenOriginalUrl(target, coordinator = null) {
  if (!target || target.nodeType !== 1 ||
      target.id !== "holdingScreenOriginalUrl" ||
      typeof target.setAttribute !== "function" || !("textContent" in target)) {
    throw new TypeError("An extension-owned holding URL element is required");
  }
  let generation = 0;
  let disposed = false;
  paint(target);

  function clear() {
    generation++;
    try { paint(target); } catch { /* never leave a previous URL visible */ }
  }
  async function show(holdingId) {
    const ticket = ++generation;
    try {
      paint(target);
      if (disposed || typeof holdingId !== "string" || !ID.test(holdingId) ||
          own(coordinator, "trustedHoldingScreenReady") !== true) return UNAVAILABLE;
      const current = own(coordinator, "readCurrentHoldingId");
      const read = own(coordinator, "readOriginalHoldingUrl");
      if (typeof current !== "function" || typeof read !== "function" ||
          current.call(coordinator) !== holdingId) return UNAVAILABLE;
      const promise = read.call(coordinator, Object.freeze({ holdingId }));
      if (!promise || typeof promise.then !== "function") return UNAVAILABLE;
      const reply = await promise;
      if (disposed || ticket !== generation ||
          own(coordinator, "trustedHoldingScreenReady") !== true ||
          own(coordinator, "readCurrentHoldingId") !== current ||
          own(coordinator, "readOriginalHoldingUrl") !== read ||
          current.call(coordinator) !== holdingId) return UNAVAILABLE;
      const url = validateOriginal(reply, holdingId);
      if (url === null) return UNAVAILABLE;
      paint(target, url);
      return DISPLAYED;
    } catch {
      if (ticket === generation) clear();
      return UNAVAILABLE;
    }
  }
  function dispose() {
    if (disposed) return;
    disposed = true;
    clear();
  }
  return Object.freeze({ show, clear, dispose });
}
