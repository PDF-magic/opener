// Exact native host extension-ID admission for a future trusted browser adapter.
// The approved list must come from a verified, locally installed host manifest.
// A caller-supplied ID or list is NOT authentication or browser attestation.
const CHROMIUM_ID = /^[a-p]{32}$/;
const FIREFOX_ID = /^(?:[A-Za-z0-9._+-]{1,64}@[A-Za-z0-9.-]{1,253}|\{[0-9a-fA-F]{8}(?:-[0-9a-fA-F]{4}){3}-[0-9a-fA-F]{12}\})$/;
const DEVELOPMENT_GECKO_ID = "pdf-magic-opener@example.invalid";
const MAX_APPROVED_IDS = 32;

function ownData(object, key) {
  if (object === null || typeof object !== "object") return undefined;
  try {
    const descriptor = Object.getOwnPropertyDescriptor(object, key);
    return descriptor && Object.hasOwn(descriptor, "value") ?
      descriptor.value : undefined;
  } catch {
    return undefined;
  }
}

// Keep a detached snapshot so another component cannot silently expand a
// vetted list after construction (especially while a port is reconnecting).
export function snapshotApprovedExtensionIds(ids) {
  try {
    if (!Array.isArray(ids) || ids.length < 1 || ids.length > MAX_APPROVED_IDS ||
        Reflect.ownKeys(ids).length !== ids.length + 1) return null;
    const copied = [];
    for (let i = 0; i < ids.length; i += 1) {
      const value = ownData(ids, String(i));
      if (typeof value !== "string") return null;
      copied.push(value);
    }
    if (new Set(copied).size !== copied.length) return null;
    return Object.freeze(copied);
  } catch {
    return null;
  }
}

export function isApprovedNativeExtensionIdentity({
  browserKind, browserRuntime, approvedExtensionIds, development = false
} = {}) {
  try {
    const valid = browserKind === "chromium" ? CHROMIUM_ID :
      browserKind === "firefox" ? FIREFOX_ID : null;
    if (valid === null) return false;
    const actualId = ownData(browserRuntime, "id");
    if (typeof actualId !== "string" || !valid.test(actualId)) return false;
    // Never treat the reserved Firefox example.invalid placeholder as a
    // production publisher identity, even when it appears in the allowlist.
    if (actualId === DEVELOPMENT_GECKO_ID && development !== true) return false;
    const approved = snapshotApprovedExtensionIds(approvedExtensionIds);
    if (approved === null) return false;
    for (const id of approved) {
      if (!valid.test(id) ||
          (id === DEVELOPMENT_GECKO_ID && development !== true)) return false;
    }
    return approved.includes(actualId); // exact, case-sensitive, no wildcards
  } catch {
    return false;
  }
}
