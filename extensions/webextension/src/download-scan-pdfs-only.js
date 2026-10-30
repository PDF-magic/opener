import { detectCompletedDownloadPdfMime } from "./download-pdf-mime.js";
import { detectCompletedPdfFilename } from "./download-pdf-filename.js";

// A scope preference is NOT consent to monitor downloads, submit scans, or
// open files. The native scanner retains every mandatory safety check.
export const SCAN_PDFS_ONLY_LABEL = "Scan PDFs Only";

function own(value, key) {
  const descriptor = Object.getOwnPropertyDescriptor(value, key);
  return descriptor && Object.hasOwn(descriptor, "value") ? descriptor.value : undefined;
}

function plain(value) {
  return value !== null && typeof value === "object" && !Array.isArray(value) &&
    [Object.prototype, null].includes(Object.getPrototypeOf(value));
}

/** Missing preferences default to PDF-only; invalid stored values fail closed. */
export function readScanPdfsOnlyPreference(configuration) {
  try {
    if (!plain(configuration)) return null;
    const descriptor = Object.getOwnPropertyDescriptor(configuration, "scanPdfsOnly");
    if (!descriptor) return true;
    return Object.hasOwn(descriptor, "value") &&
      typeof descriptor.value === "boolean" ? descriptor.value : null;
  } catch {
    return null;
  }
}

/**
 * An ID-correlated browser metadata *candidate* filter. Callers must obtain
 * explicit consent and downloads permission before retrieving the records.
 * Both records must be from the same completed download, and the trusted
 * native coordinator MUST independently verify actual bytes and scan policy.
 * "included" never authorizes scanning, skipping scans, or opening files.
 */
export function considerDownloadForScan(configuration, mimeRecord, filenameRecord) {
  try {
    const pdfsOnly = readScanPdfsOnlyPreference(configuration);
    if (pdfsOnly === null) return null;
    const mime = detectCompletedDownloadPdfMime(mimeRecord);
    const filename = detectCompletedPdfFilename(filenameRecord);
    if (!mime || !filename || mime.id !== filename.id ||
        mime.authorizesOpen !== false || filename.authorizesOpen !== false) return null;
    const pdfCandidate = mime.isPdfMime === true || filename.isPdfFilename === true;
    return Object.freeze({
      id: mime.id,
      pdfCandidate,
      included: !pdfsOnly || pdfCandidate,
      authorizesScan: false,
      authorizesOpen: false
    });
  } catch {
    return null;
  }
}

const unavailable = Object.freeze({ status: "unavailable", scanPdfsOnly: null });
function ready(value) {
  return Object.freeze({ status: "ready", scanPdfsOnly: value });
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
 * A user-controlled checkbox in a separately reviewed extension-owned settings
 * UI. The injected store must read the saved configuration and atomically
 * write ONLY scanPdfsOnly, preserving unrelated user preferences. Nothing is
 * read/written until load() or an actual trusted change event is requested.
 */
export function createScanPdfsOnlySetting(root, store) {
  if (!validRoot(root)) throw new TypeError("An extension-owned settings element is required");
  let active = true;
  let generation = 0;
  let checkbox = null;
  let listener = null;
  let state = unavailable;

  function detach() {
    if (checkbox && listener) checkbox.removeEventListener("change", listener);
    checkbox = null;
    listener = null;
    root.replaceChildren();
    root.hidden = true;
  }

  function clear() {
    generation += 1;
    detach();
    state = unavailable;
  }

  function methods() {
    try {
      if (!plain(store)) return null;
      const read = own(store, "readConfiguration");
      const save = own(store, "saveScanPdfsOnly");
      return typeof read === "function" && typeof save === "function"
        ? { read, save } : null;
    } catch {
      return null;
    }
  }

  async function load() {
    clear();
    const ticket = generation;
    const api = methods();
    if (!active || !api) return state;
    try {
      const pending = api.read.call(store);
      if (!pending || typeof pending.then !== "function") return state;
      const saved = readScanPdfsOnlyPreference(await pending);
      if (!active || ticket !== generation || saved === null) return state;

      const label = root.ownerDocument.createElement("label");
      const input = root.ownerDocument.createElement("input");
      input.type = "checkbox";
      input.checked = saved;
      const title = root.ownerDocument.createElement("span");
      title.textContent = SCAN_PDFS_ONLY_LABEL;
      label.append(input, title);
      const help = root.ownerDocument.createElement("p");
      help.textContent = "Limit future download-scan candidates to browser-identified PDFs. Disabling this option does not enable scanning other file types. Mandatory native scanner checks still apply.";
      const message = root.ownerDocument.createElement("p");
      message.setAttribute("role", "status");
      message.setAttribute("aria-live", "polite");
      message.textContent = "";

      async function onChange(event) {
        if (!active || ticket !== generation || event?.isTrusted !== true ||
            event?.target !== input || input.disabled || state.status !== "ready") {
          input.checked = state.status === "ready" ? state.scanPdfsOnly : saved;
          return;
        }
        const previous = state.scanPdfsOnly;
        const next = input.checked;
        if (next === previous) return;
        input.disabled = true;
        message.textContent = "Saving download preference…";
        try {
          const request = api.save.call(store, next);
          if (!request || typeof request.then !== "function" || await request !== true) {
            throw new Error("save not confirmed");
          }
          const recheck = api.read.call(store);
          if (!recheck || typeof recheck.then !== "function" ||
              readScanPdfsOnlyPreference(await recheck) !== next) {
            throw new Error("saved value not confirmed");
          }
          if (!active || ticket !== generation) return;
          state = ready(next);
          message.textContent = "Download preference saved.";
        } catch {
          if (!active || ticket !== generation) return;
          input.checked = previous;
          message.textContent = "Could not confirm the preference. Review your saved settings.";
        } finally {
          if (active && ticket === generation) input.disabled = false;
        }
      }

      checkbox = input;
      listener = onChange;
      input.addEventListener("change", onChange);
      root.replaceChildren(label, help, message);
      root.hidden = false;
      state = ready(saved);
    } catch {
      if (active && ticket === generation) clear();
    }
    return state;
  }

  function dispose() {
    if (!active) return;
    active = false;
    clear();
  }

  clear();
  return Object.freeze({ load, clear, dispose, state: () => state });
}
