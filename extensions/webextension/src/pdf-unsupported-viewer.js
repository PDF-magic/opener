import { detectPrivilegedPdfViewer } from "./pdf-privileged-viewer.js";
import { detectJavascriptPdfViewer } from "./pdf-js-viewer.js";
import { getPdfInterceptionPointAssessment } from "./pdf-interception-point-assessment.js";

// Passive and browser-neutral fallback for PDF viewers that a future
// automatic interception integration cannot safely hold or inspect.
// Never infer scanner success from a browser's viewer shell.
const CONTEXT_FIELDS = Object.freeze([
  "tabId", "frameId", "url", "viewerKind", "trustedBrowserEvent"
]);
const KINDS = new Set([
  "document", "browser-owned", "site-scripted",
  "embedded", "plugin", "unknown"
]);
const MAX_URL_LENGTH = 8192;

function own(value, key) {
  const descriptor = Object.getOwnPropertyDescriptor(value, key);
  return descriptor && Object.hasOwn(descriptor, "value") ?
    descriptor.value : undefined;
}

function exactContext(value) {
  if (value === null || typeof value !== "object" || Array.isArray(value) ||
      ![Object.prototype, null].includes(Object.getPrototypeOf(value))) return false;
  const keys = Reflect.ownKeys(value);
  return keys.length === CONTEXT_FIELDS.length &&
    keys.every(key => typeof key === "string" && CONTEXT_FIELDS.includes(key)) &&
    CONTEXT_FIELDS.every(key => {
      const descriptor = Object.getOwnPropertyDescriptor(value, key);
      return descriptor && Object.hasOwn(descriptor, "value");
    });
}

function decision(status, reason, viewerType = "unverified") {
  return Object.freeze({
    status, reason, viewerType,
    // The browser may display/open the PDF independently of this extension.
    browserPreviewBlocked: false,
    interceptionVerified: false,
    pdfBytesVerified: false,
    scanVerified: false,
    mayRedirectToHoldingScreen: false,
    mayFetchViewerDocument: false,
    mayInitiateAutomaticScan: false,
    mayAutomaticallyOpen: false,
    authorizesScan: false,
    authorizesOpen: false,
    // The explicit route must still perform eligibility, consent and native checks.
    nextStep: status === "not-a-viewer" ? "none" :
      "offer-explicit-scan-after-eligibility-check"
  });
}

const UNTRUSTED = decision("untrusted-context", "missing-verified-browser-event");
const UNKNOWN_BROWSER = decision("untrusted-context", "unsupported-browser");
const NOT_VIEWER = decision("not-a-viewer", "no-viewer-evidence", "none");

/**
 * Conservatively assess unsupported PDF viewer implementations.
 *
 * The coordinator must authenticate the browser-supplied event and classify
 * viewerKind independently from trusted browser state. The Boolean field is
 * NOT itself authentication and must never be supplied by untrusted page JS.
 * This helper does not register interception listeners or open anything.
 *
 * "Unsupported" means PDF Magic Opener has NOT established control over the
 * viewer's rendering or opening path, not that the browser cannot display PDF.
 */
export function assessUnsupportedPdfViewer(browserId, context) {
  try {
    const browser = getPdfInterceptionPointAssessment(browserId);
    if (browser.browserId === null) return UNKNOWN_BROWSER;
    if (!exactContext(context) || own(context, "trustedBrowserEvent") !== true) {
      return UNTRUSTED;
    }

    const tabId = own(context, "tabId");
    const frameId = own(context, "frameId");
    const rawUrl = own(context, "url");
    const kind = own(context, "viewerKind");
    if (!Number.isSafeInteger(tabId) || tabId < 0 ||
        !Number.isSafeInteger(frameId) || frameId < 0 ||
        typeof rawUrl !== "string" || !rawUrl.length ||
        rawUrl.length > MAX_URL_LENGTH ||
        /[\u0000-\u0020\u007f]/u.test(rawUrl) || !KINDS.has(kind)) return UNTRUSTED;

    const url = new URL(rawUrl);
    if (url.username || url.password) return UNTRUSTED;

    const details = { tabId, frameId, url: rawUrl };
    const native = detectPrivilegedPdfViewer(details);
    if (native.isPrivilegedPdfViewer) {
      // An authentic browser-owned viewer shell is not evidence of PDF bytes.
      // Do not assume Chromium URLs belong to Firefox or vice versa.
      const chromeViewer = url.protocol === "chrome-extension:";
      if ((chromeViewer && browser.family !== "chromium") ||
          (!chromeViewer && browserId !== "firefox")) {
        return decision("unverified-viewer", "viewer-browser-mismatch");
      }
      return decision("unsupported-viewer", "browser-owned-shell", "browser-owned");
    }

    // Only a documented PDF.js URL pattern with an eligible same-origin file
    // hint can identify this kind of site-hosted viewer; still not PDF bytes.
    if (detectJavascriptPdfViewer(details).isPdfCandidate) {
      return decision("unsupported-viewer", "site-pdfjs-rendering", "site-scripted");
    }

    // Custom canvases, plugins and embedded viewer surfaces cannot be held
    // by a navigation-URL suffix or a late DOM observation.
    if (kind === "site-scripted" || kind === "plugin" || kind === "embedded") {
      return decision("unsupported-viewer", "uncontrolled-viewer-rendering", kind);
    }
    if (kind === "browser-owned" || kind === "unknown" ||
        ["chrome:", "edge:", "about:", "resource:", "moz-extension:",
          "chrome-extension:", "safari-extension:"].includes(url.protocol)) {
      return decision("unverified-viewer", "unrecognized-viewer");
    }
    return NOT_VIEWER;
  } catch {
    // Hostile getter, proxy, malformed URL or metadata cannot initiate scans.
    return UNTRUSTED;
  }
}
