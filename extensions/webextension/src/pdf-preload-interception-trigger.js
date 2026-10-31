import {
  identifyPdfPreRenderNavigationEvent
} from "./pdf-pre-render-navigation-events.js";
import {
  getPdfInterceptionPointAssessment
} from "./pdf-interception-point-assessment.js";

// Nonblocking navigation/load notifications are never a pre-render veto.
// This excludes late notifications even if a URL has a .pdf suffix.
export const NON_BLOCKING_PDF_LIFECYCLE_EVENTS = Object.freeze([
  "webNavigation.onCommitted",
  "webNavigation.onDOMContentLoaded",
  "webNavigation.onCompleted",
  "webNavigation.onErrorOccurred",
  "webNavigation.onHistoryStateUpdated",
  "webNavigation.onReferenceFragmentUpdated",
  "webRequest.onCompleted",
  "downloads.onCreated",
  "downloads.onChanged",
  "downloads.onErased",
  "tabs.onUpdated"
]);

const NON_BLOCKING = new Set(NON_BLOCKING_PDF_LIFECYCLE_EVENTS);

function decision(browserId, event, status, phase, pdfEvidence, candidate = false) {
  return Object.freeze({
    browserId, event, status, phase, pdfEvidence,
    // A candidate must still prove blocking API support, effective grants,
    // a verified current request, PDF byte completeness and native scanning.
    conditionalPreRequestBlockingCandidate: candidate,
    effectiveBlockingPointVerified: false,
    permissionVerified: false,
    pdfBytesVerified: false,
    nativeScanVerified: false,
    mayInitiateAutomaticInterception: false,
    allPdfOpeningPathsBlocked: false,
    authorizesScan: false,
    authorizesOpen: false
  });
}

const UNKNOWN = decision(null, "unavailable", "unsupported-browser", "unknown", "none");

/**
 * Classify a trusted browser-provided event as a possible pre-load
 * interception trigger without ever enabling interception.
 *
 * A pre-render notification is not necessarily a blocking API. In particular,
 * webNavigation notifications, response-header observations, redirect notices
 * and download events must never be treated as a synchronous PDF-open veto.
 * The only event-stage candidate is a main-frame webRequest.onBeforeRequest
 * on a browser with a separately documented conditional blocking point.
 * Chrome/Edge normal MV3 installations do NOT have that blocking capability;
 * enterprise-policy installation, actual permissions, and per-version
 * behavior have to be proved by a separate feature.
 *
 * This function is pure. It neither registers listeners nor reads raw URLs
 * from browser globals; the existing event classifier validates supplied
 * top-frame details and strips any sensitive URLs and headers.
 */
export function assessPdfPreLoadInterceptionTrigger(browserId, event, details) {
  const assessment = getPdfInterceptionPointAssessment(browserId);
  if (assessment.browserId === null) return UNKNOWN;
  if (typeof event !== "string") {
    return decision(browserId, "unavailable", "unknown-event", "unknown", "none");
  }

  // Reject nonblocking or too-late phases *before* inspecting metadata. A
  // committed navigation may be pre-load but still cannot veto the request.
  if (NON_BLOCKING.has(event)) {
    return decision(browserId, event, "nonblocking-lifecycle-observation", "not-a-veto", "none");
  }

  const observation = identifyPdfPreRenderNavigationEvent(event, details);
  if (observation.event === "unavailable") {
    return decision(browserId, "unavailable", "invalid-or-unavailable-event",
      "unknown", "none");
  }

  if (event === "webRequest.onBeforeRequest") {
    const point = assessment.requestBlockingListenerPoint;
    if (point === "firefox-blocking-request-with-host-and-api-grants") {
      return decision(browserId, event, "conditional-firefox-request-block",
        observation.stage, observation.pdfEvidence, true);
    }
    if (point === "enterprise-policy-installed-only" ||
        point === "conditional-enterprise-policy-installed-only") {
      return decision(browserId, event, "conditional-enterprise-request-block",
        observation.stage, observation.pdfEvidence, true);
    }
    return decision(browserId, event, "no-blocking-listener-established",
      observation.stage, observation.pdfEvidence);
  }

  // A navigation-start event may arrive early but has no synchronous veto.
  // A response-header hint may arrive before body processing but cannot
  // guarantee a complete hold until the native scanner returns a verdict.
  // Redirect notices cannot authenticate the final PDF destination.
  return decision(browserId, event, "early-observation-only",
    observation.stage, observation.pdfEvidence);
}
