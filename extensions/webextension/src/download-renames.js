// Opt-in observation of browser-reported filename changes during downloads.
// No downloaded paths, previous filenames, URLs, or bytes leave this module.
const MAX_ACTIVE_DOWNLOADS = 256;
const MAX_FILENAME_LENGTH = 4096;

function own(object, key) {
  if (!object || typeof object !== "object" || Array.isArray(object) ||
      ![Object.prototype, null].includes(Object.getPrototypeOf(object))) return undefined;
  const descriptor = Object.getOwnPropertyDescriptor(object, key);
  return descriptor && Object.hasOwn(descriptor, "value") ? descriptor.value : undefined;
}

const validId = (id) => Number.isSafeInteger(id) && id >= 0;
const validFilename = (name) => typeof name === "string" &&
  name.length > 0 && name.length <= MAX_FILENAME_LENGTH &&
  !/[\u0000-\u001f\u007f]/u.test(name);

/**
 * Subscribe to filename changes only for downloads observed in progress.
 * The trusted caller must separately obtain the optional downloads permission
 * and monitoring consent. No permission is requested here. The only emitted
 * value is an immutable { kind: "renamed", id }; a filename change is not proof
 * of a PDF, scan verdict, file access, or authorization to open a document.
 *
 * Browser downloads.onChanged provides a { previous, current } filename
 * delta. Comparing those values within the callback avoids retaining paths
 * even in memory. A first assignment (missing previous) is not a rename.
 */
export function subscribeToDownloadRenames(downloadsApi, onRenamed, { onError } = {}) {
  if (typeof onRenamed !== "function" ||
      (onError !== undefined && typeof onError !== "function")) {
    throw new TypeError("A rename notification callback is required");
  }

  const kinds = ["onCreated", "onChanged", "onErased"];
  const sources = kinds.map((name) => {
    const event = downloadsApi?.[name];
    if (typeof event?.addListener !== "function" ||
        typeof event?.removeListener !== "function") {
      throw new TypeError("A complete downloads event source is required");
    }
    return event;
  });

  const activeIds = new Set();
  const subscriptions = [];
  let listening = false;
  const notifyError = () => {
    try { onError?.(new Error("Download rename callback failed")); }
    catch { /* Never expose untrusted browser metadata or caller exceptions. */ }
  };
  const startTracking = (id) => {
    activeIds.delete(id);
    if (activeIds.size === MAX_ACTIVE_DOWNLOADS) {
      activeIds.delete(activeIds.values().next().value);
    }
    activeIds.add(id);
  };
  const handlers = [
    (item) => {
      const id = own(item, "id");
      if (!validId(id)) return;
      activeIds.delete(id); // A browser ID may be reused for a new transfer.
      if (own(item, "state") === "in_progress") startTracking(id);
    },
    (delta) => {
      const id = own(delta, "id");
      if (!validId(id) || !activeIds.has(id)) return;
      const stateDescriptor = Object.getOwnPropertyDescriptor(delta, "state");
      if (stateDescriptor) {
        if (!Object.hasOwn(stateDescriptor, "value")) return;
        const state = own(stateDescriptor.value, "current");
        if (state === "complete" || state === "interrupted") {
          activeIds.delete(id);
          return;
        }
        if (state !== "in_progress") return;
      }
      const filename = own(delta, "filename");
      const previous = own(filename, "previous");
      const current = own(filename, "current");
      if (!validFilename(previous) || !validFilename(current) || previous === current) return;
      onRenamed(Object.freeze({ kind: "renamed", id }));
    },
    (id) => {
      if (validId(id)) activeIds.delete(id);
    }
  ];

  try {
    for (let index = 0; index < sources.length; index++) {
      const listener = (payload) => {
        if (!listening) return;
        try { handlers[index](payload); }
        catch { notifyError(); }
      };
      sources[index].addListener(listener);
      subscriptions.push({ source: sources[index], listener });
    }
    listening = true;
  } catch {
    for (const { source, listener } of subscriptions.reverse()) {
      try { source.removeListener(listener); } catch { /* best effort */ }
    }
    throw new TypeError("Cannot register download rename observers");
  }

  return function unsubscribeDownloadRenames() {
    if (!listening) return;
    listening = false;
    activeIds.clear();
    for (const { source, listener } of subscriptions.reverse()) {
      try { source.removeListener(listener); } catch { notifyError(); }
    }
  };
}
