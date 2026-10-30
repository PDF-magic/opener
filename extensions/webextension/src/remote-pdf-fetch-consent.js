import { describeExplicitPdfScanRequest } from "./explicit-pdf-scan-request.js";

// Fail-closed, one-attempt consent boundary. The installed extension remains
// inert: this module never starts network access or registers browser listeners.
export const REMOTE_PDF_FETCH_CONSENT_NOTICE =
  "Fetch this selected PDF from the displayed website for a local security scan? " +
  "This contacts the site and may download a copy. Declining leaves it untouched.";

const outcomes = Object.freeze(Object.fromEntries(
  ["not-requested", "unavailable", "denied", "duplicate", "ended", "fetch-requested"]
    .map(name => [name, Object.freeze({
      status: name, consentGranted: name === "fetch-requested",
      fetchRequested: name === "fetch-requested", scanVerified: false,
      authorizesScan: false, authorizesOpen: false
    })])
));
const ID = /^[A-Za-z0-9_-]{1,80}$/u;
const REQUIRED = Object.freeze([
  "tabId", "frameId", "selectionId", "resourceId", "siteOrigin",
  "verified", "permissionGranted"
]);

function own(value, key) {
  if (value === null || (typeof value !== "object" && typeof value !== "function")) {
    return undefined;
  }
  const property = Object.getOwnPropertyDescriptor(value, key);
  return property && Object.hasOwn(property, "value") ? property.value : undefined;
}

function method(value, key) {
  const found = own(value, key);
  return typeof found === "function" ? found : null;
}

function canonicalHttpsOrigin(origin) {
  if (typeof origin !== "string" || origin.length > 260 ||
      /[\u0000-\u0020\u007f]/u.test(origin)) return false;
  const url = new URL(origin);
  const labels = url.hostname.split(".");
  return url.protocol === "https:" && url.origin === origin &&
    url.pathname === "/" && !url.search && !url.hash &&
    !url.username && !url.password && !url.port &&
    labels.length >= 2 && url.hostname.length <= 253 &&
    /^[a-z]{2,63}$/u.test(labels.at(-1)) &&
    labels.every(label => label.length <= 63 &&
      /^[a-z0-9](?:[a-z0-9-]*[a-z0-9])?$/u.test(label));
}

function verifiedSelection(record, request) {
  if (record === null || typeof record !== "object" || Array.isArray(record) ||
      ![Object.prototype, null].includes(Object.getPrototypeOf(record))) return null;
  const keys = Reflect.ownKeys(record);
  if (keys.length !== REQUIRED.length ||
      !keys.every(key => typeof key === "string" && REQUIRED.includes(key))) return null;
  const fields = Object.create(null);
  for (const key of REQUIRED) {
    const property = Object.getOwnPropertyDescriptor(record, key);
    if (!property || !Object.hasOwn(property, "value")) return null;
    fields[key] = property.value;
  }
  if (fields.tabId !== request.tabId || fields.frameId !== request.frameId ||
      fields.selectionId !== request.selectionId ||
      typeof fields.resourceId !== "string" || !ID.test(fields.resourceId) ||
      !canonicalHttpsOrigin(fields.siteOrigin) ||
      fields.verified !== true || fields.permissionGranted !== true) return null;
  return Object.freeze({
    tabId: fields.tabId, frameId: fields.frameId,
    selectionId: fields.selectionId, resourceId: fields.resourceId,
    siteOrigin: fields.siteOrigin
  });
}

function identical(a, b) {
  return Boolean(a && b &&
    ["tabId", "frameId", "selectionId", "resourceId", "siteOrigin"]
      .every(key => a[key] === b[key]));
}

/**
 * A separately reviewed, trusted browser-to-native adapter injects three
 * OWN methods: readVerifiedRemotePdfSelection (synchronous, network-free),
 * promptForRemotePdfFetchConsent (user-visible Promise<boolean>), and
 * requestVerifiedRemotePdfFetch (Promise<{accepted:true}>).
 * It must also supply remotePdfFetchReady: true.
 *
 * requestFetchAfterConsent must be called in a real user gesture; its
 * userInitiated boolean is NOT proof of one. The consent UI is invoked
 * synchronously before the first await. After an explicit affirmative
 * response, the selected PDF identity and site grant are checked again.
 * Redirects, actual PDF identity, native ClamAV and scan-before-open policy
 * remain obligations of the independently authenticated coordinator.
 */
export function createRemotePdfFetchConsentGate(coordinator = null) {
  const attempted = new Set();
  let ended = false;
  let generation = 0;

  async function requestFetchAfterConsent(request) {
    if (ended) return outcomes.ended;
    const details = describeExplicitPdfScanRequest(request);
    if (!details) return outcomes["not-requested"];
    if (attempted.has(details.requestId)) return outcomes.duplicate;
    if (attempted.size >= 256) return outcomes.unavailable;
    // Consume the ID even on refusal/error; no consent is reused or cached.
    attempted.add(details.requestId);
    const version = generation;
    try {
      if (own(coordinator, "remotePdfFetchReady") !== true) return outcomes.unavailable;
      const read = method(coordinator, "readVerifiedRemotePdfSelection");
      const prompt = method(coordinator, "promptForRemotePdfFetchConsent");
      const acquire = method(coordinator, "requestVerifiedRemotePdfFetch");
      if (!read || !prompt || !acquire) return outcomes.unavailable;
      const reference = Object.freeze({
        requestId: details.requestId, source: details.source,
        tabId: details.tabId, frameId: details.frameId,
        selectionId: details.selectionId
      });
      const before = verifiedSelection(read.call(coordinator, reference), details);
      if (!before) return outcomes.unavailable;
      const notice = Object.freeze({
        siteOrigin: before.siteOrigin, source: details.source,
        notice: REMOTE_PDF_FETCH_CONSENT_NOTICE
      });
      // Prompt inside the direct click callback, before an asynchronous wait.
      const answer = prompt.call(coordinator, notice);
      if (!answer || typeof answer.then !== "function") return outcomes.unavailable;
      if ((await answer) !== true) return outcomes.denied;
      if (ended || version !== generation ||
          own(coordinator, "remotePdfFetchReady") !== true ||
          method(coordinator, "readVerifiedRemotePdfSelection") !== read ||
          method(coordinator, "requestVerifiedRemotePdfFetch") !== acquire) {
        return outcomes.unavailable;
      }
      const after = verifiedSelection(read.call(coordinator, reference), details);
      if (!identical(before, after)) return outcomes.unavailable;
      // Only opaque resource identity; never send a remote URL, local file
      // path, document bytes, browser clean claim or native open instruction.
      const pending = acquire.call(coordinator, Object.freeze({
        requestId: details.requestId, source: details.source,
        tabId: after.tabId, frameId: after.frameId,
        selectionId: after.selectionId, resourceId: after.resourceId,
        siteOrigin: after.siteOrigin
      }));
      if (!pending || typeof pending.then !== "function") return outcomes.unavailable;
      const acknowledged = await pending;
      if (ended || version !== generation ||
          own(acknowledged, "accepted") !== true) return outcomes.unavailable;
      // Only an acquisition request was accepted, not a verified clean scan.
      return outcomes["fetch-requested"];
    } catch {
      // No browser/native error details, private URLs or paths escape.
      return outcomes.unavailable;
    }
  }

  function dispose() {
    ended = true;
    generation++;
    attempted.clear();
    return outcomes.ended;
  }

  return Object.freeze({ requestFetchAfterConsent, dispose });
}
