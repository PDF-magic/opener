import { detectPdfNavigation } from "./pdf-navigation.js";
import { classifyHtmlOrPdfResponse } from "./pdf-response-mime.js";

// A documentation-backed timeline of *potentially observable* browser events.
// This is not a listener, an interception point, or a rendering-time guarantee.
// The relative order of webNavigation and webRequest events is NOT defined.
export const PDF_NAVIGATION_EVENT_PHASES = Object.freeze([
  Object.freeze({ event: "webNavigation.onBeforeNavigate", stage: "before-navigation", potentiallyBeforeRender: true }),
  Object.freeze({ event: "webRequest.onBeforeRequest", stage: "before-network-request", potentiallyBeforeRender: true }),
  Object.freeze({ event: "webRequest.onBeforeRedirect", stage: "before-redirect", potentiallyBeforeRender: true }),
  Object.freeze({ event: "webRequest.onHeadersReceived", stage: "response-headers", potentiallyBeforeRender: true }),
  Object.freeze({ event: "webNavigation.onCommitted", stage: "committed", potentiallyBeforeRender: false }),
  Object.freeze({ event: "webNavigation.onDOMContentLoaded", stage: "dom-loaded", potentiallyBeforeRender: false }),
  Object.freeze({ event: "webNavigation.onCompleted", stage: "navigation-completed", potentiallyBeforeRender: false }),
  Object.freeze({ event: "webNavigation.onErrorOccurred", stage: "navigation-error", potentiallyBeforeRender: false }),
  Object.freeze({ event: "webRequest.onCompleted", stage: "request-completed", potentiallyBeforeRender: false })
]);

const PHASES = new Map(PDF_NAVIGATION_EVENT_PHASES.map(entry => [entry.event, entry]));
const NONE = Object.freeze({
  event: "unavailable", stage: "unknown", potentiallyBeforeRender: false,
  pdfEvidence: "none", verifiedPdf: false,
  interceptionEnabled: false, authorizesScan: false, authorizesOpen: false
});

function own(value, key) {
  if (value === null || typeof value !== "object") return undefined;
  const descriptor = Object.getOwnPropertyDescriptor(value, key);
  return descriptor && Object.hasOwn(descriptor, "value") ? descriptor.value : undefined;
}

function validTopFrame(details, navigation) {
  if (details === null || typeof details !== "object" ||
      Array.isArray(details) ||
      ![Object.prototype, null].includes(Object.getPrototypeOf(details))) return false;
  const tabId = own(details, "tabId");
  if (!Number.isSafeInteger(tabId) || tabId < 0 ||
      own(details, "frameId") !== 0) return false;
  // webNavigation events have no HTTP resource 'type' field; webRequest
  // must be an actual main-frame document request, never a PDF-named asset.
  return navigation || own(details, "type") === "main_frame";
}

/**
 * Classify the lifecycle stage of a trusted browser-provided top-frame event.
 *
 * The early events *may* precede inline PDF rendering on supported routes,
 * but API events are not guaranteed for PDFs, internal viewers, cached/blob
 * documents, or every browser. In particular, an async callback is NOT a
 * synchronous veto. No URL/headers are retained, and no scan or open is
 * authorized. A separate authenticated integration must supply the event.
 */
export function identifyPdfPreRenderNavigationEvent(event, details) {
  try {
    if (typeof event !== "string" || !PHASES.has(event)) return NONE;
    const navigation = event.startsWith("webNavigation.");
    if (!validTopFrame(details, navigation)) return NONE;
    const phase = PHASES.get(event);
    let pdfEvidence = "none";
    if (event === "webNavigation.onBeforeNavigate" ||
        event === "webRequest.onBeforeRequest") {
      if (detectPdfNavigation(details).isPdfCandidate) {
        pdfEvidence = "url-path-hint";
      }
    } else if (event === "webRequest.onHeadersReceived") {
      // A final response can be extensionless or can be HTML at a .pdf URL.
      // The response-MIME classifier deliberately ignores filename/URL hints.
      const response = classifyHtmlOrPdfResponse(details);
      if (response.isPdfCandidate) pdfEvidence = "response-mime-hint";
      else if (response.isHtmlPage) pdfEvidence = "html-response";
    }
    // Redirects are not the final resource; a previous .pdf URL is not
    // proof that the redirected destination will render as a PDF.
    return Object.freeze({
      event, stage: phase.stage,
      potentiallyBeforeRender: phase.potentiallyBeforeRender,
      pdfEvidence, verifiedPdf: false, interceptionEnabled: false,
      authorizesScan: false, authorizesOpen: false
    });
  } catch {
    // No browser URLs, headers, filenames or native diagnostics in results.
    return NONE;
  }
}
