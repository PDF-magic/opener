// Opt-in, extension-owned presentation of a *verified native* scan result.
// Browser download sizes, MIME types and request-submitted acknowledgments are
// never evidence of a scanner file-size failure.
const REQUEST_ID = /^[A-Za-z0-9_-]{1,80}$/u;
const unavailable = Object.freeze({
  status: "unavailable", fileSizeFailure: false, authorizesOpen: false
});
const displayed = Object.freeze({
  status: "displayed", fileSizeFailure: true, authorizesOpen: false
});

function own(value, key) {
  if (value === null || typeof value !== "object") return undefined;
  const descriptor = Object.getOwnPropertyDescriptor(value, key);
  return descriptor && Object.hasOwn(descriptor, "value")
    ? descriptor.value : undefined;
}

function exact(value, keys) {
  if (value === null || typeof value !== "object" || Array.isArray(value) ||
      ![Object.prototype, null].includes(Object.getPrototypeOf(value))) return false;
  const actual = Reflect.ownKeys(value);
  return actual.length === keys.length && keys.every(key => actual.includes(key)) &&
    keys.every(key => Object.hasOwn(Object.getOwnPropertyDescriptor(value, key), "value"));
}

function verifiedFileSizeFailure(response, scanRequestId) {
  try {
    if (!exact(response, ["scanRequestId", "report"]) ||
        own(response, "scanRequestId") !== scanRequestId) return false;
    const report = own(response, "report");
    if (!exact(report, ["schemaVersion", "authorizesOpen", "requiresBlock",
      "scan", "clamav", "structuralFindings"]) ||
        own(report, "schemaVersion") !== 1 ||
        own(report, "authorizesOpen") !== false ||
        own(report, "requiresBlock") !== true) return false;

    const scan = own(report, "scan");
    if (!exact(scan, ["status"]) ||
        own(scan, "status") !== "fileTooLarge") return false;
    const clamav = own(report, "clamav");
    if (!exact(clamav, ["effectivePolicyId", "detectionNames"]) ||
        own(clamav, "effectivePolicyId") !== "built-in") return false;
    const detections = own(clamav, "detectionNames");
    // A report with detections must never be downgraded to a size-only
    // warning, even when the other fields contradict one another.
    if (!Array.isArray(detections) || detections.length !== 0 ||
        Reflect.ownKeys(detections).length !== 1) return false;
    const structural = own(report, "structuralFindings");
    // The structural payload is not rendered, but it must be a separate
    // ordinary data object, never an accessor or an unknown primitive.
    if (!structural || typeof structural !== "object" ||
        Array.isArray(structural) ||
        ![Object.prototype, null].includes(Object.getPrototypeOf(structural))) return false;
    return true;
  } catch {
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
 * Render a canonical, correlated fileTooLarge report from an independently
 * authenticated native coordinator into an extension-owned DOM element.
 * No import-time activity, browser API, native messaging, or scan initiation.
 */
export function createDownloadFileSizeFailureDisplay(root, coordinator) {
  if (!validRoot(root)) {
    throw new TypeError("An extension-owned display element is required");
  }
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
      const response = await pending;
      if (!active || ticket !== generation ||
          own(coordinator, "nativeScanResultsReady") !== true ||
          !verifiedFileSizeFailure(response, scanRequestId)) return unavailable;

      // Fixed text avoids invented size thresholds and leaking paths, raw
      // scanner diagnostics, browser metadata or untrusted report content.
      const heading = root.ownerDocument.createElement("strong");
      heading.textContent = "File too large — scanning blocked";
      const explanation = root.ownerDocument.createElement("p");
      explanation.textContent =
        "The required scanner could not fully inspect this PDF because a file-size limit was exceeded. The PDF was not opened.";
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
