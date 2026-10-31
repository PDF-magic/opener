import { getPdfInterceptionPointAssessment } from "./pdf-interception-point-assessment.js";

// Classifications are about what a browser observation COULD establish, not
// whether any listener is installed or native scan has succeeded (opener-0798).
export const PDF_INTERCEPTION_ASSURANCE_KINDS = Object.freeze([
  "inactive",
  "best-effort-monitoring",
  "unverified-request-blocking-candidate"
]);

const OBSERVATION_ONLY = new Set([
  "webNavigation.onBeforeNavigate",
  "webNavigation.onCommitted",
  "webNavigation.onDOMContentLoaded",
  "webNavigation.onCompleted",
  "webNavigation.onErrorOccurred",
  "webNavigation.onHistoryStateUpdated",
  "webNavigation.onReferenceFragmentUpdated",
  "webRequest.onBeforeRedirect",
  "webRequest.onHeadersReceived",
  "webRequest.onCompleted",
  "declarativeNetRequest.onRuleMatchedDebug",
  "downloads.onCreated",
  "downloads.onChanged",
  "downloads.onErased",
  "tabs.onUpdated"
]);

const LABELS = Object.freeze({
  inactive: "Automatic PDF interception inactive",
  "best-effort-monitoring": "Best-effort monitoring — PDF opening is not blocked",
  "unverified-request-blocking-candidate":
    "Unverified request-blocking candidate — not scan-before-open enforcement"
});

function result(browserId, observation, status, kind, potentialBlockingPoint = false) {
  return Object.freeze({
    browserId,
    observation,
    status,
    assuranceKind: kind,
    displayLabel: LABELS[kind],
    // A matching network-request block does not equate to complete response
    // containment or native PDF scan-before-rendering.
    scope: kind === "inactive" ? "none" :
      potentialBlockingPoint ? "matching-network-requests-only" :
        "browser-event-observation-only",
    potentialBlockingPoint,
    activeMonitoringVerified: false,
    effectiveRequestBlockingVerified: false,
    nativeScanBeforeRenderVerified: false,
    allPdfOpeningPathsBlocked: false,
    mayClaimEnforcedProtection: false,
    authorizesScan: false,
    authorizesOpen: false
  });
}

const UNKNOWN_BROWSER = result(null, null, "unsupported-browser", "inactive");
const UNKNOWN_OBSERVATION = browserId =>
  result(browserId, null, "unknown-observation", "inactive");

/**
 * Describe the assurance level of one *reported* browser signal.
 *
 * Caller-supplied signals are NOT trusted evidence that the event happened.
 * The extension currently has no active interception or proven blocking
 * scanner interlock. This passive classifier must never advertise an enforced
 * PDF scan-before-open, even when a caller reports a blocking API or clean
 * native scan. An authenticated future coordinator must separately prove
 * effective permissions, request blocking/response holding, byte completeness,
 * native scan freshness and file identity before any stronger claim.
 *
 * No browser events are subscribed, no permissions requested, no scanned PDF
 * opened, and no user configuration is read or changed.
 */
export function describePdfInterceptionAssurance(browserId, observation = null) {
  const browser = getPdfInterceptionPointAssessment(browserId);
  if (browser.browserId === null) return UNKNOWN_BROWSER;
  if (observation === null) {
    return result(browserId, null, "inactive", "inactive");
  }
  if (typeof observation !== "string") return UNKNOWN_OBSERVATION(browserId);

  if (OBSERVATION_ONLY.has(observation)) {
    return result(browserId, observation, "observation-only",
      "best-effort-monitoring");
  }
  if (observation === "webRequest.onBeforeRequest") {
    const isCandidate = browser.requestBlockingListenerPoint !== "not-established";
    return isCandidate ?
      result(browserId, observation, "blocking-point-unverified",
        "unverified-request-blocking-candidate", true) :
      result(browserId, observation, "observation-only",
        "best-effort-monitoring");
  }
  return UNKNOWN_OBSERVATION(browserId);
}
