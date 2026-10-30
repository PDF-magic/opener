export const OPEN_SCANNED_PDF_LABEL = "Open Scanned PDF";
export const OPEN_SCANNED_PDF_UNAVAILABLE_MESSAGE =
  "Open Scanned PDF is unavailable until a verified clean scan and trusted native opening service are connected.";

const ID = /^[A-Za-z0-9_-]{1,80}$/u;
const STATUS = Object.freeze({
  unavailable: Object.freeze({
    status: "unavailable", enabled: false, scanVerified: false,
    authorizesOpen: false, opened: false
  }),
  offered: Object.freeze({
    status: "offered", enabled: true, scanVerified: false,
    authorizesOpen: false, opened: false
  }),
  pending: Object.freeze({
    status: "pending", enabled: false, scanVerified: false,
    authorizesOpen: false, opened: false
  }),
  submitted: Object.freeze({
    status: "request-submitted", enabled: false, scanVerified: false,
    authorizesOpen: false, opened: false
  })
});
const HELP =
  "Opens only after the native scanner rechecks the clean result, file integrity, quarantine and your selected PDF application.";
const PENDING = "Open requested; checking the scan again.";
const QUEUED = "Opening requested. Native safety checks must still approve it.";
const REFUSED = "Opening is unavailable. The PDF was not confirmed opened.";

function own(value, key) {
  if (value === null || (typeof value !== "object" && typeof value !== "function")) {
    return undefined;
  }
  const descriptor = Object.getOwnPropertyDescriptor(value, key);
  return descriptor && Object.hasOwn(descriptor, "value") ? descriptor.value : undefined;
}

function exact(value, fields) {
  if (value === null || typeof value !== "object" || Array.isArray(value) ||
      ![Object.prototype, null].includes(Object.getPrototypeOf(value))) return false;
  const actual = Reflect.ownKeys(value);
  return actual.length === fields.length &&
    actual.every(key => typeof key === "string" && fields.includes(key)) &&
    fields.every(key => {
      const d = Object.getOwnPropertyDescriptor(value, key);
      return d && Object.hasOwn(d, "value");
    });
}

function cleanReport(message, requestId, scanRequestId) {
  if (!exact(message, ["version", "kind", "topic", "requestId", "payload"]) ||
      own(message, "version") !== 1 || own(message, "kind") !== "response" ||
      own(message, "topic") !== "scan.result" ||
      own(message, "requestId") !== requestId) return false;
  const p = own(message, "payload");
  if (!exact(p, ["scanRequestId", "status", "result", "scanCompleted",
    "scanVerified", "authorizesOpen"]) ||
      own(p, "scanRequestId") !== scanRequestId ||
      own(p, "status") !== "complete" ||
      own(p, "scanCompleted") !== true ||
      own(p, "scanVerified") !== true ||
      own(p, "authorizesOpen") !== false) return false;
  const result = own(p, "result");
  return exact(result, ["status"]) && own(result, "status") === "clean";
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
 * Inactive explicit "Open Scanned PDF" button, owned by the extension UI.
 *
 * The injected coordinator must independently authenticate the native scan
 * session and the selected PDF; browser JSON and page data are NOT proof.
 * It must revalidate the *actual file*, current ClamAV signatures, quarantine
 * and user-configured opening application at final native handoff.
 *
 * A shared per-native-session gate is required to prevent duplicate commands
 * from separate popup views. No raw file path, URL, or verdict crosses the
 * open-request boundary. Accepted means queued, never opened.
 */
export function createOpenScannedPdfAction(root, coordinator, gate) {
  if (!validRoot(root)) throw new TypeError("An extension-owned element is required");
  let active = true;
  let generation = 0;
  let button = null;
  let listener = null;
  let state = STATUS.unavailable;

  function ready() {
    return own(coordinator, "nativeScanResultsReady") === true &&
      own(coordinator, "nativeVerifiedOpeningReady") === true &&
      typeof own(coordinator, "readCurrentSelectionId") === "function" &&
      typeof own(coordinator, "readVerifiedExplicitPdfScanResult") === "function" &&
      typeof own(coordinator, "requestVerifiedExplicitPdfOpen") === "function" &&
      typeof own(gate, "requestOpenOnce") === "function";
  }

  function hide() {
    if (button && listener) button.removeEventListener("click", listener);
    button = null;
    listener = null;
    root.replaceChildren();
    root.hidden = true;
  }

  function clear() {
    generation += 1;
    hide();
    state = STATUS.unavailable;
  }

  async function offer({ requestId, scanRequestId, selectionId } = {}) {
    clear();
    if (!active || ![requestId, scanRequestId, selectionId].every(
      id => typeof id === "string" && ID.test(id)
    ) || !ready()) return state;
    const ticket = generation;
    try {
      const currentSelection = own(coordinator, "readCurrentSelectionId");
      const read = own(coordinator, "readVerifiedExplicitPdfScanResult");
      const open = own(coordinator, "requestVerifiedExplicitPdfOpen");
      const reference = Object.freeze({ requestId, scanRequestId, selectionId });
      function isCurrent() {
        try {
          return active && generation === ticket && ready() &&
            own(coordinator, "readCurrentSelectionId") === currentSelection &&
            own(coordinator, "readVerifiedExplicitPdfScanResult") === read &&
            own(coordinator, "requestVerifiedExplicitPdfOpen") === open &&
            currentSelection.call(coordinator) === selectionId;
        } catch {
          return false;
        }
      }
      async function verifyClean() {
        if (!isCurrent()) return false;
        const promise = read.call(coordinator, reference);
        if (!promise || typeof promise.then !== "function") return false;
        const report = await promise;
        return isCurrent() && cleanReport(report, requestId, scanRequestId);
      }
      if (!await verifyClean()) return state;
      const choice = root.ownerDocument.createElement("button");
      choice.type = "button";
      choice.textContent = OPEN_SCANNED_PDF_LABEL;
      const explanation = root.ownerDocument.createElement("p");
      explanation.textContent = HELP;
      explanation.setAttribute("role", "status");
      explanation.setAttribute("aria-live", "polite");

      async function click(event) {
        if (event?.isTrusted !== true ||
            state !== STATUS.offered || choice.disabled) return;
        if (!isCurrent()) {
          choice.disabled = true;
          state = STATUS.unavailable;
          explanation.textContent = REFUSED;
          return;
        }
        choice.disabled = true;
        state = STATUS.pending;
        explanation.textContent = PENDING;
        try {
          // A previously clean result can become stale after a file change,
          // navigation, signature update or revoked permission. Recheck.
          if (!await verifyClean()) throw new Error("scan not current");
          const outcome = await gate.requestOpenOnce(scanRequestId, async () => {
            if (!isCurrent()) return { accepted: false };
            const pending = open.call(coordinator, Object.freeze({ scanRequestId }));
            if (!pending || typeof pending.then !== "function") {
              return { accepted: false };
            }
            const acknowledgement = await pending;
            // Acknowledgement is not a clean verdict or proof of opening.
            return isCurrent() &&
              exact(acknowledgement, ["accepted", "scanRequestId"]) &&
              own(acknowledgement, "accepted") === true &&
              own(acknowledgement, "scanRequestId") === scanRequestId
              ? { accepted: true } : { accepted: false };
          });
          if (!active || generation !== ticket) return;
          if (!isCurrent() || own(outcome, "status") !== "command-submitted") {
            state = STATUS.unavailable;
            explanation.textContent = REFUSED;
            return;
          }
          state = STATUS.submitted;
          explanation.textContent = QUEUED;
        } catch {
          if (!active || generation !== ticket) return;
          state = STATUS.unavailable;
          explanation.textContent = REFUSED;
        }
      }

      choice.addEventListener("click", click);
      button = choice;
      listener = click;
      root.replaceChildren(choice, explanation);
      root.hidden = false;
      state = STATUS.offered;
    } catch {
      if (generation === ticket) clear();
    }
    return state;
  }

  function dispose() {
    if (!active) return;
    active = false;
    clear();
  }
  clear();
  return Object.freeze({ offer, clear, state: () => state, dispose });
}
