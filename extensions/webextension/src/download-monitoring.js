// Passive, browser-neutral download event adapter (opener-0570).
// Callers must explicitly supply a browser downloads API with permission.
// Download metadata is untrusted: this module does not identify PDFs,
// inspect content, send data, scan files, or authorize application opening.

const eventKinds = ["created", "changed", "erased"];
const metadataFields = ["filename", "mime", "state", "danger", "error"];
const maxMetadataLength = 4096;

function validId(value) {
  return Number.isSafeInteger(value) && value >= 0;
}

function metadata(value) {
  return typeof value === "string" &&
    value.length <= maxMetadataLength && !value.includes("\0") ? value : null;
}

/**
 * Reduce untrusted browser events to an immutable, explicitly allowlisted
 * subset. Never forward URLs, referrers, headers, cookies or download bytes.
 * State and danger remain browser-supplied strings, never security verdicts.
 */
export function normalizeDownloadEvent(kind, payload) {
  // WebExtensions downloads.onErased passes a numeric id, not a record.
  if (kind === "erased" && validId(payload)) payload = { id: payload };
  if (!eventKinds.includes(kind) || payload === null ||
      typeof payload !== "object" || !validId(payload.id)) {
    return null;
  }

  const event = { kind, id: payload.id };
  if (kind !== "erased") {
    for (const field of metadataFields) {
      // Browser downloads.onChanged uses { current, previous } deltas.
      // Creation events use plain properties. Never forward previous values.
      const raw = kind === "changed" ? payload[field]?.current : payload[field];
      const value = metadata(raw);
      if (value !== null) event[field] = value;
    }
  }
  return Object.freeze(event);
}

/**
 * Register portable downloads.onCreated/onChanged/onErased listeners only
 * when explicitly invoked with a trusted browser downloads event source.
 * The returned unsubscribe is idempotent and detaches all three listeners.
 * No permissions are requested and no global browser/chrome APIs are used.
 */
export function subscribeToDownloadEvents(downloadsApi, onEvent, { onError } = {}) {
  if (typeof onEvent !== "function" ||
      (onError !== undefined && typeof onError !== "function")) {
    throw new TypeError("A download event callback is required");
  }

  const registrations = eventKinds.map((kind) => {
    const source = downloadsApi?.["on" + kind[0].toUpperCase() + kind.slice(1)];
    if (typeof source?.addListener !== "function" ||
        typeof source?.removeListener !== "function") {
      throw new TypeError("A complete browser downloads event source is required");
    }
    return { kind, source };
  });

  let active = false;
  const registered = [];
  try {
    for (const registration of registrations) {
      const listener = (payload) => {
        if (!active) return;
        const event = normalizeDownloadEvent(registration.kind, payload);
        if (event === null) return;
        try {
          onEvent(event);
        } catch (error) {
          // Consumer exceptions cannot crash a browser's download dispatch.
          try { onError?.(error); } catch { /* caller error handling is isolated */ }
        }
      };
      registration.source.addListener(listener);
      registered.push({ source: registration.source, listener });
    }
    active = true;
  } catch (error) {
    for (const { source, listener } of registered.reverse()) {
      try { source.removeListener(listener); } catch { /* best-effort rollback */ }
    }
    throw error;
  }

  return function unsubscribe() {
    if (!active) return;
    active = false;
    for (const { source, listener } of registered.reverse()) {
      try { source.removeListener(listener); } catch { /* callbacks remain disabled */ }
    }
  };
}
