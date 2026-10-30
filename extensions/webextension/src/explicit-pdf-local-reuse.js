// Reuse an independently verified, already local PDF before proposing a new
// source acquisition. This never downloads, reads files, scans or opens PDFs.
const SNAPSHOT_FIELDS = Object.freeze([
  "selectionId", "documentRevision", "pdfIdentified",
  "currentDocumentVerified", "selectionVerified",
  "permissionGranted", "userInitiated"
]);
const LOCAL_FIELDS = Object.freeze([
  "selectionId", "documentRevision", "status",
  "identityVerified", "transferComplete", "fileStable"
]);

const unavailable = Object.freeze({
  status: "unavailable", canReuseLocal: false, requiresAcquisition: false,
  downloadStarted: false, authorizesDownload: false,
  scanVerified: false, authorizesScan: false, authorizesOpen: false
});
const reuse = Object.freeze({
  status: "reuse-existing-local", canReuseLocal: true, requiresAcquisition: false,
  downloadStarted: false, authorizesDownload: false,
  scanVerified: false, authorizesScan: false, authorizesOpen: false
});
const missing = Object.freeze({
  status: "source-acquisition-needed", canReuseLocal: false, requiresAcquisition: true,
  downloadStarted: false, authorizesDownload: false,
  scanVerified: false, authorizesScan: false, authorizesOpen: false
});

function own(record, key) {
  const descriptor = Object.getOwnPropertyDescriptor(record, key);
  return descriptor && Object.hasOwn(descriptor, "value")
    ? descriptor.value : undefined;
}

function exactRecord(value, keys) {
  if (value === null || typeof value !== "object" || Array.isArray(value) ||
      ![Object.prototype, null].includes(Object.getPrototypeOf(value))) return false;
  const actual = Reflect.ownKeys(value);
  return actual.length === keys.length &&
    actual.every(key => typeof key === "string" && keys.includes(key));
}

function selectionId(value) {
  return typeof value === "string" && value.length >= 1 && value.length <= 80 &&
    /^[A-Za-z0-9_-]+$/u.test(value);
}

function validSnapshot(record, selected) {
  if (!exactRecord(record, SNAPSHOT_FIELDS) ||
      own(record, "selectionId") !== selected ||
      !Number.isSafeInteger(own(record, "documentRevision")) ||
      own(record, "documentRevision") < 0) return false;
  return SNAPSHOT_FIELDS.slice(2).every(key => own(record, key) === true);
}

function validLocalInspection(result, id, revision) {
  if (!result || typeof result !== "object") return null;
  if (exactRecord(result, ["selectionId", "documentRevision", "status"]) &&
      own(result, "selectionId") === id &&
      own(result, "documentRevision") === revision &&
      own(result, "status") === "not-present") return missing;
  if (exactRecord(result, LOCAL_FIELDS) &&
      own(result, "selectionId") === id &&
      own(result, "documentRevision") === revision &&
      own(result, "status") === "verified-local" &&
      own(result, "identityVerified") === true &&
      own(result, "transferComplete") === true &&
      own(result, "fileStable") === true) return reuse;
  return null;
}

/**
 * An explicit current-document source-selection policy. A separately
 * authenticated, trusted coordinator is responsible for obtaining the
 * current selection, locating an existing local copy and independently
 * checking that its identity, completeness and stability match the PDF.
 *
 * Only a positive, matching, rechecked local result is reusable. A definitive
 * "not-present" result proposes later acquisition but never authorizes or
 * starts it. Ambiguous, partial, stale and failed checks fail closed; the
 * caller must not interpret them as permission to download again.
 *
 * No path, URL, file bytes or browser metadata crosses this boundary.
 * An actual scan must still independently verify the real file and native
 * ClamAV/signature freshness/quarantine/scan-before-open requirements.
 */
export async function planExplicitPdfLocalReuse({ coordinator, selectionId: selected } = {}) {
  try {
    if (!selectionId(selected) || coordinator === null ||
        (typeof coordinator !== "object" && typeof coordinator !== "function") ||
        own(coordinator, "localPdfReuseReady") !== true) return unavailable;
    const current = own(coordinator, "readCurrentPdfSelection");
    const inspect = own(coordinator, "inspectExistingLocalPdf");
    if (typeof current !== "function" || typeof inspect !== "function") return unavailable;

    const before = current.call(coordinator);
    if (!validSnapshot(before, selected)) return unavailable;
    const revision = own(before, "documentRevision");
    // A reference to an opaque selection, not a URL or filesystem path.
    const lookup = Object.freeze({ selectionId: selected, documentRevision: revision });
    const inspection = await inspect.call(coordinator, lookup);
    const choice = validLocalInspection(inspection, selected, revision);
    // A changed coordinator callback can refer to a different document or
    // native session. Do not consult a captured, stale callback after await.
    if (!choice || own(coordinator, "localPdfReuseReady") !== true ||
        own(coordinator, "readCurrentPdfSelection") !== current ||
        own(coordinator, "inspectExistingLocalPdf") !== inspect) return unavailable;

    // Invalidate a result if navigation, permission, document identity or
    // user selection changed during the asynchronous local-file inspection.
    const after = current.call(coordinator);
    if (!validSnapshot(after, selected) ||
        own(after, "documentRevision") !== revision) return unavailable;

    return choice;
  } catch {
    // Do not expose paths, URLs, native errors or privileged browser state.
    return unavailable;
  }
}
