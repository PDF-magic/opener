import { describeExplicitPdfScanRequest } from "./explicit-pdf-scan-request.js";

// Preserve the user's source page during an explicitly initiated PDF scan.
// This is a passive, opt-in browser-coordinator contract: no tab/navigation
// APIs, listeners, remote requests, file access, native scanning or opening.
export const ORIGINAL_PAGE_PRESERVATION_POLICY = "leave-original-tab-open";

const ID = /^[A-Za-z0-9_-]{1,80}$/u;
const PAGE_FIELDS = Object.freeze([
  "requestId", "tabId", "frameId", "selectionId",
  "pageId", "documentRevision", "pageKind", "verified",
  "permissionGranted"
]);
const MAX_ATTEMPTS = 128;

function response(status, applicable = false, preserved = false) {
  return Object.freeze({
    status, originalPageApplicable: applicable,
    originalPagePreserved: preserved,
    navigationRequested: false,
    scanVerified: false, authorizesScan: false, authorizesOpen: false
  });
}

const NOT_REQUESTED = response("not-requested");
const UNAVAILABLE = response("unavailable");
const DUPLICATE = response("duplicate");
const ENDED = response("ended");

function own(value, field) {
  if (value === null || (typeof value !== "object" &&
      typeof value !== "function")) return undefined;
  const descriptor = Object.getOwnPropertyDescriptor(value, field);
  return descriptor && Object.hasOwn(descriptor, "value") ?
    descriptor.value : undefined;
}

function exactRecord(value, fields) {
  if (value === null || typeof value !== "object" || Array.isArray(value) ||
      ![Object.prototype, null].includes(Object.getPrototypeOf(value))) return false;
  const keys = Reflect.ownKeys(value);
  return keys.length === fields.length &&
    keys.every(key => typeof key === "string" && fields.includes(key)) &&
    fields.every(field => {
      const descriptor = Object.getOwnPropertyDescriptor(value, field);
      return descriptor && Object.hasOwn(descriptor, "value");
    });
}

function verifiedPage(value, intent) {
  if (!exactRecord(value, PAGE_FIELDS) ||
      own(value, "requestId") !== intent.requestId ||
      own(value, "tabId") !== intent.tabId ||
      own(value, "frameId") !== intent.frameId ||
      own(value, "selectionId") !== intent.selectionId ||
      own(value, "verified") !== true ||
      own(value, "permissionGranted") !== true) return null;

  const pageId = own(value, "pageId");
  const revision = own(value, "documentRevision");
  const pageKind = own(value, "pageKind");
  if (typeof pageId !== "string" || !ID.test(pageId) ||
      pageId === intent.requestId || pageId === intent.selectionId ||
      !Number.isSafeInteger(revision) || revision < 0 ||
      !["html-page", "pdf-viewer"].includes(pageKind) ||
      (intent.source !== "toolbar" && pageKind !== "html-page")) return null;

  // The opaque pageId refers to the original TOP-LEVEL tab document, even
  // when the selected PDF is inside an iframe in that tab.
  return Object.freeze({
    pageId, documentRevision: revision, pageKind
  });
}

function samePage(left, right) {
  return Boolean(left && right && left.pageId === right.pageId &&
    left.documentRevision === right.documentRevision &&
    left.pageKind === right.pageKind);
}

/**
 * Request an explicit PDF scan while keeping the original website tab.
 *
 * The separately reviewed coordinator must own:
 * - originalPagePreservationReady: true
 * - readVerifiedOriginalPage(reference): synchronous, network-free, exact
 *   PAGE_FIELDS snapshot from trusted browser tab/document state
 * - requestPdfScanWithoutNavigation(reference): Promise<{accepted:true}>.
 *
 * The callback MUST use existing download/native scanner interfaces without
 * navigating, replacing, closing, focusing away from, or reopening the source
 * tab. The guard never restores an old URL, replays a signed link, opens a new
 * page, or grants native scan/open authorization. The final snapshot detects
 * a changed/discarded page, but cannot undo navigation by a misbehaving host.
 */
export function createExplicitPdfOriginalPagePreservation(coordinator = null) {
  const attempted = new Set();
  let disposed = false;
  let generation = 0;

  async function requestScan(request) {
    if (disposed) return ENDED;
    try {
      const intent = describeExplicitPdfScanRequest(request);
      if (!intent) return NOT_REQUESTED;
      if (attempted.has(intent.requestId)) return DUPLICATE;
      if (attempted.size >= MAX_ATTEMPTS ||
          own(coordinator, "originalPagePreservationReady") !== true) {
        return UNAVAILABLE;
      }

      const read = own(coordinator, "readVerifiedOriginalPage");
      const submit = own(coordinator, "requestPdfScanWithoutNavigation");
      if (typeof read !== "function" || typeof submit !== "function") {
        return UNAVAILABLE;
      }
      const reference = Object.freeze({
        requestId: intent.requestId, source: intent.source,
        tabId: intent.tabId, frameId: intent.frameId,
        selectionId: intent.selectionId
      });
      const before = verifiedPage(read.call(coordinator, reference), intent);
      if (!before) return UNAVAILABLE;

      // Reserve synchronously, before invoking any potentially asynchronous
      // coordinator. A replay cannot submit a second download/scan request.
      attempted.add(intent.requestId);
      const version = generation;
      const scoped = Object.freeze({
        ...reference, pageId: before.pageId,
        documentRevision: before.documentRevision,
        preservationPolicy: ORIGINAL_PAGE_PRESERVATION_POLICY
      });

      // Call in the initiating event handler, before the first await. The
      // coordinator must independently verify the genuine browser gesture.
      const pending = submit.call(coordinator, scoped);
      if (!pending || typeof pending.then !== "function") return UNAVAILABLE;
      const acknowledgment = await pending;
      if (disposed || generation !== version ||
          own(coordinator, "originalPagePreservationReady") !== true ||
          own(coordinator, "readVerifiedOriginalPage") !== read ||
          own(coordinator, "requestPdfScanWithoutNavigation") !== submit ||
          !exactRecord(acknowledgment, ["accepted"]) ||
          own(acknowledgment, "accepted") !== true) return UNAVAILABLE;

      const after = verifiedPage(read.call(coordinator, reference), intent);
      if (!samePage(before, after)) return UNAVAILABLE;

      // A standalone PDF-viewer tab has no original HTML page to preserve.
      // Neither outcome grants scanning, opening, or automatic navigation.
      return response("request-submitted",
        before.pageKind === "html-page", before.pageKind === "html-page");
    } catch {
      // Browser exceptions can contain source URLs or private document paths.
      return UNAVAILABLE;
    }
  }

  function dispose() {
    disposed = true;
    generation++;
    attempted.clear();
    return ENDED;
  }

  return Object.freeze({ requestScan, dispose });
}
