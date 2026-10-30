// Explicit, per-session private-browsing consent gate (opener-0594).
// This module neither observes private sessions nor requests browser permissions.
// No browser APIs, listeners, storage, native bridges, or scanner operations run
// on import or when the gate is constructed.

export const PRIVATE_BROWSING_CONSENT_NOTICE =
  "Private browsing access is optional. Enable it only for this private session; " +
  "the extension must also be allowed in private browsing in your browser settings.";

const states = Object.freeze({
  "consent-required": Object.freeze({
    status: "consent-required", consentRecorded: false,
    scannerVerified: false, authorizesOpen: false
  }),
  consented: Object.freeze({
    status: "consented", consentRecorded: true,
    scannerVerified: false, authorizesOpen: false
  }),
  unavailable: Object.freeze({
    status: "unavailable", consentRecorded: false,
    scannerVerified: false, authorizesOpen: false
  }),
  ended: Object.freeze({
    status: "ended", consentRecorded: false,
    scannerVerified: false, authorizesOpen: false
  })
});

function ownMethod(object, name) {
  if (object === null || (typeof object !== "object" && typeof object !== "function")) {
    return null;
  }
  try {
    const descriptor = Object.getOwnPropertyDescriptor(object, name);
    return descriptor && "value" in descriptor && typeof descriptor.value === "function" ?
      descriptor.value : null;
  } catch {
    return null;
  }
}

/**
 * Create an independent, memory-only consent gate for ONE verified private
 * browsing session. A trusted future UI provides the selected browser's
 * extension API plus a session-bound verifyPrivateSession() function that
 * returns Promise<true> only while that same private session is active.
 *
 * recordConsent({userInitiated:true}) must be invoked directly from a genuine
 * user opt-in action. The flag is a caller assertion, NOT proof of a gesture.
 * Browser-level permission alone cannot grant application-level consent.
 *
 * canProcessPrivateData() rechecks browser access and session identity on
 * EVERY operation. No successful check confers PDF scanner approval or
 * authorization to open a file. Caller must still enforce its own gates.
 */
export function createPrivateBrowsingConsentGate(extensionApi, verifyPrivateSession) {
  const checkIncognitoAccess = ownMethod(extensionApi, "isAllowedIncognitoAccess");
  const checkSession = typeof verifyPrivateSession === "function" ?
    verifyPrivateSession : null;

  let status = "consent-required";
  let ended = false;
  let generation = 0;
  let recorded = false;
  let attempt = null;

  function state() {
    return states[status];
  }

  async function verifyCurrentAccess() {
    if (!checkIncognitoAccess || !checkSession) return false;
    try {
      // Require Promise-style browser verification; callback-only and
      // unsupported browsers fail closed rather than inferring permission.
      const browserCheck = checkIncognitoAccess.call(extensionApi);
      if (!browserCheck || typeof browserCheck.then !== "function" ||
          (await browserCheck) !== true) return false;
      // Session verification is separate from the browser's extension grant.
      const sessionCheck = checkSession();
      return Boolean(sessionCheck && typeof sessionCheck.then === "function" &&
        (await sessionCheck) === true);
    } catch {
      return false; // Never expose browser or private-window error details.
    }
  }

  function recordConsent({ userInitiated = false } = {}) {
    if (ended) return Promise.resolve(states.ended);
    if (userInitiated !== true) return Promise.resolve(state());
    if (attempt) return status === "unavailable" ? Promise.resolve(state()) : attempt;
    // Never reprompt or silently renew consent.

    const version = generation;
    attempt = (async () => {
      const verified = await verifyCurrentAccess();
      if (ended || version !== generation) return state();
      recorded = verified;
      status = verified ? "consented" : "unavailable";
      return state();
    })();
    return attempt;
  }

  async function canProcessPrivateData() {
    if (ended || !recorded) return false;
    const version = generation;
    const verified = await verifyCurrentAccess();
    if (ended || version !== generation || !recorded) return false;
    if (!verified) {
      // Revocation, an ended/private-context mismatch, or an API failure
      // invalidates the consent gate. A new explicit opt-in is required.
      generation++;
      recorded = false;
      status = "unavailable";
      return false;
    }
    return true;
  }

  function endSession() {
    generation++;
    ended = true;
    recorded = false;
    status = "ended";
    return state();
  }

  return Object.freeze({ state, recordConsent, canProcessPrivateData, endSession });
}
