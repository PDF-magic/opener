// Opt-in Open After Scanning action for an independently authenticated
// native scanner coordinator. It never launches a PDF or treats browser
// completion, a clean label, or a submitted scan as opening authorization.
export const OPEN_AFTER_SCANNING_LABEL = "Open After Scanning";
const REQUEST_ID = /^[A-Za-z0-9_-]{1,80}$/u;
const HELP = "The PDF opens only if native scanning, file integrity, quarantine and selected-application checks succeed.";
const PENDING = "Open requested; waiting for the native scanner.";
const ACCEPTED = "Open requested. The native scanner must still approve opening.";
const REFUSED = "Open After Scanning is unavailable. The PDF was not opened.";
const STATES = Object.freeze({
  unavailable: Object.freeze({
    status: "unavailable", enabled: false, scanVerified: false, authorizesOpen: false
  }),
  offered: Object.freeze({
    status: "offered", enabled: true, scanVerified: false, authorizesOpen: false
  }),
  pending: Object.freeze({
    status: "pending", enabled: false, scanVerified: false, authorizesOpen: false
  }),
  requested: Object.freeze({
    status: "request-submitted", enabled: false, scanVerified: false, authorizesOpen: false
  })
});

function own(value, key) {
  if (value === null || (typeof value !== "object" && typeof value !== "function")) {
    return undefined;
  }
  const descriptor = Object.getOwnPropertyDescriptor(value, key);
  return descriptor && Object.hasOwn(descriptor, "value") ? descriptor.value : undefined;
}

function validRoot(root) {
  try {
    return root?.nodeType === 1 &&
      typeof root.ownerDocument?.createElement === "function" &&
      typeof root.replaceChildren === "function";
  } catch {
    return false;
  }
}

/**
 * Supply only an extension-owned UI element and a separately authenticated
 * coordinator. The coordinator must independently correlate its own scan
 * session, verify current scanner/permission state, and enforce every native
 * ClamAV, signature freshness, byte/identity, quarantine, app preference and
 * final opening gate. Its readiness flag alone is NOT authentication.
 *
 * A click requests a future native opening IF all safety gates succeed. No
 * download path, browser metadata or claimed verdict is ever passed here.
 */
export function createDownloadOpenAfterScanningAction(root, coordinator) {
  if (!validRoot(root)) throw new TypeError("An extension-owned element is required");
  let active = true;
  let generation = 0;
  let button = null;
  let clickHandler = null;
  let status = STATES.unavailable;

  function available() {
    return own(coordinator, "nativeOpenAfterScanningReady") === true &&
      typeof own(coordinator, "requestOpenAfterScanning") === "function";
  }

  function hide() {
    if (button && clickHandler) button.removeEventListener("click", clickHandler);
    button = null;
    clickHandler = null;
    root.replaceChildren();
    root.hidden = true;
  }

  function clear() {
    generation += 1;
    hide();
    status = STATES.unavailable;
  }

  function offer(scanRequestId) {
    clear();
    if (!active) return status;
    try {
      if (typeof scanRequestId !== "string" ||
          !REQUEST_ID.test(scanRequestId) || !available()) return status;

      const ticket = generation;
      const choice = root.ownerDocument.createElement("button");
      choice.type = "button";
      choice.textContent = OPEN_AFTER_SCANNING_LABEL;
      const explanation = root.ownerDocument.createElement("p");
      explanation.textContent = HELP;
      explanation.setAttribute("role", "status");
      explanation.setAttribute("aria-live", "polite");

      async function onClick(event) {
        // Browser-generated click includes keyboard and accessibility
        // activation. Script-dispatched clicks cannot request a native open.
        if (event?.isTrusted !== true || !active || generation !== ticket ||
            choice.disabled || status !== STATES.offered) return;
        choice.disabled = true; // Reserve synchronously before any await.
        status = STATES.pending;
        explanation.textContent = PENDING;
        try {
          if (!available()) throw new Error("native coordinator unavailable");
          const send = own(coordinator, "requestOpenAfterScanning");
          // A fixed exact-ID-only request. The native coordinator must check
          // correlation and all scan/open gates independently at handoff.
          const request = Object.freeze({ scanRequestId });
          const pending = send.call(coordinator, request);
          if (!pending || typeof pending.then !== "function") {
            throw new Error("native coordinator did not acknowledge asynchronously");
          }
          const acknowledgement = await pending;
          if (!active || generation !== ticket) return;
          if (!available() || own(acknowledgement, "accepted") !== true) {
            status = STATES.unavailable;
            explanation.textContent = REFUSED;
            return;
          }
          // Accepted is only an intent; it is NEVER a clean scan, an actual
          // file opening, or authority to bypass the native quarantine gate.
          status = STATES.requested;
          explanation.textContent = ACCEPTED;
        } catch {
          if (!active || generation !== ticket) return;
          status = STATES.unavailable;
          explanation.textContent = REFUSED;
        }
      }

      button = choice;
      clickHandler = onClick;
      choice.addEventListener("click", onClick);
      root.replaceChildren(choice, explanation);
      root.hidden = false;
      status = STATES.offered;
    } catch {
      clear();
    }
    return status;
  }

  function state() {
    return status;
  }

  function dispose() {
    if (!active) return;
    active = false;
    clear();
  }

  clear();
  return Object.freeze({ offer, state, clear, dispose });
}
