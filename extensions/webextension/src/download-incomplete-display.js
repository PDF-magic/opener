// Opt-in, fail-closed display for a trusted native download scan that did
// not complete. Neither browser download metadata nor a scan submission
// acknowledgment can establish this terminal status.
const REQUEST_ID = /^[A-Za-z0-9_-]{1,80}$/u;
const SIGNATURE = /^[A-Za-z0-9][A-Za-z0-9._!+@-]{0,254}$/u;
const MAX_DETECTIONS = 256;
const unavailable = Object.freeze({
  status: "unavailable", incompleteScan: false, authorizesOpen: false
});
const displayed = Object.freeze({
  status: "displayed", incompleteScan: true, authorizesOpen: false
});

function own(value, key) {
  if (value === null || typeof value !== "object") return undefined;
  const property = Object.getOwnPropertyDescriptor(value, key);
  return property && Object.hasOwn(property, "value") ? property.value : undefined;
}

function exact(value, keys) {
  if (value === null || typeof value !== "object" || Array.isArray(value) ||
      ![Object.prototype, null].includes(Object.getPrototypeOf(value))) return false;
  const actual = Reflect.ownKeys(value);
  return actual.length === keys.length && keys.every((key) => actual.includes(key)) &&
    keys.every((key) => Object.hasOwn(Object.getOwnPropertyDescriptor(value, key), "value"));
}

function isVerifiedIncompleteScan(response, requestId) {
  try {
    if (!exact(response, ["scanRequestId", "report"]) ||
        own(response, "scanRequestId") !== requestId) return false;
    const report = own(response, "report");
    if (!exact(report, ["schemaVersion", "authorizesOpen", "requiresBlock",
      "scan", "clamav", "structuralFindings"]) ||
        own(report, "schemaVersion") !== 1 ||
        own(report, "authorizesOpen") !== false ||
        own(report, "requiresBlock") !== true ||
        !exact(own(report, "scan"), ["status"]) ||
        own(own(report, "scan"), "status") !== "incompleteScan") return false;
    const clamav = own(report, "clamav");
    if (!exact(clamav, ["effectivePolicyId", "detectionNames"]) ||
        own(clamav, "effectivePolicyId") !== "built-in") return false;
    const names = own(clamav, "detectionNames");
    if (!Array.isArray(names) || names.length > MAX_DETECTIONS ||
        Reflect.ownKeys(names).length !== names.length + 1) return false;
    const seen = new Set();
    for (let index = 0; index < names.length; index += 1) {
      const name = own(names, String(index));
      if (typeof name !== "string" || !SIGNATURE.test(name) ||
          seen.has(name)) return false;
      seen.add(name);
    }
    // Structural details are evidence only; never show raw findings or paths.
    const structural = own(report, "structuralFindings");
    return structural !== null && typeof structural === "object" &&
      !Array.isArray(structural) &&
      [Object.prototype, null].includes(Object.getPrototypeOf(structural));
  } catch {
    // Hostile native objects, accessors or proxies cannot create an alert.
    return false;
  }
}

function validRoot(root) {
  try {
    return root?.nodeType === 1 &&
      typeof root.ownerDocument?.createElement === "function" &&
      typeof root.replaceChildren === "function" &&
      typeof root.setAttribute === "function" &&
      typeof root.removeAttribute === "function";
  } catch {
    return false;
  }
}

/**
 * Render only a correlated canonical incompleteScan result from an
 * independently authenticated native coordinator. The readiness flag itself
 * is NOT authentication. This module never connects to a host, starts
 * scanning, opens files, or enables the inactive WebExtension background.
 */
export function createDownloadIncompleteScanDisplay(root, coordinator) {
  if (!validRoot(root)) throw new TypeError("An extension-owned display element is required");
  let active = true;
  let generation = 0;

  function hide() {
    root.replaceChildren();
    root.hidden = true;
    root.removeAttribute("role");
  }

  function clear() {
    generation += 1;
    hide();
  }

  async function show(scanRequestId) {
    const ticket = ++generation;
    hide();
    try {
      if (!active || typeof scanRequestId !== "string" ||
          !REQUEST_ID.test(scanRequestId) ||
          own(coordinator, "nativeScanResultsReady") !== true) return unavailable;
      const read = own(coordinator, "readVerifiedDownloadScanReport");
      if (typeof read !== "function") return unavailable;
      const pending = read.call(coordinator, scanRequestId);
      if (!pending || typeof pending.then !== "function") return unavailable;
      const result = await pending;
      if (!active || ticket !== generation ||
          own(coordinator, "nativeScanResultsReady") !== true ||
          !isVerifiedIncompleteScan(result, scanRequestId)) return unavailable;

      // Fixed text is deliberately separate from malware detections and
      // scanner failures. No raw native reason, filename or finding is shown.
      const heading = root.ownerDocument.createElement("strong");
      heading.textContent = "Scan incomplete — opening stopped";
      const explanation = root.ownerDocument.createElement("p");
      explanation.textContent =
        "The required safety scan did not finish. This PDF cannot be opened until the scan completes successfully.";
      if (!active || ticket !== generation) return unavailable;
      root.replaceChildren(heading, explanation);
      root.setAttribute("role", "alert");
      root.hidden = false;
      return displayed;
    } catch {
      if (active && ticket === generation) hide();
      return unavailable;
    }
  }

  function dispose() {
    if (!active) return;
    active = false;
    clear();
  }

  hide();
  return Object.freeze({ show, clear, dispose });
}
