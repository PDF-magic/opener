// Apply the *installed* scan policy to a trusted download submission boundary.
// Planned Standard/Enhanced/Maximum preview choices are NOT active policies.
// This module neither reads browser storage nor starts native messaging.
const POLICY_ID = "built-in";
const requiredChecks = Object.freeze([
  "clamav_scan_gate", "signature_freshness", "file_integrity", "fail_closed_handoff"
]);
const policy = Object.freeze({
  profileId: POLICY_ID,
  requiredChecks,
  failureDisposition: "deny"
});
const rejected = Object.freeze({ accepted: false });
const accepted = Object.freeze({ accepted: true, effectivePolicyId: POLICY_ID });

function own(value, key) {
  if (value === null || typeof value !== "object") return undefined;
  const descriptor = Object.getOwnPropertyDescriptor(value, key);
  return descriptor && Object.hasOwn(descriptor, "value") ? descriptor.value : undefined;
}

function activeSelection(configuration) {
  if (configuration === null || typeof configuration !== "object" ||
      Array.isArray(configuration) ||
      ![Object.prototype, null].includes(Object.getPrototypeOf(configuration))) return false;
  // A missing key means the installation's documented Built-in default.
  // An EXPLICIT invalid or planned selection fails closed; do not replace it.
  const descriptor = Object.getOwnPropertyDescriptor(configuration, "selectedProtectionProfile");
  return descriptor === undefined ||
    (Object.hasOwn(descriptor, "value") && descriptor.value === POLICY_ID);
}

function validRequest(request) {
  if (request === null || typeof request !== "object" || Array.isArray(request) ||
      ![Object.prototype, null].includes(Object.getPrototypeOf(request))) return false;
  const keys = Reflect.ownKeys(request);
  if (keys.length !== 2 || !keys.includes("id") || !keys.includes("localPath")) return false;
  const id = own(request, "id");
  const path = own(request, "localPath");
  return Number.isSafeInteger(id) && id >= 0 && typeof path === "string" &&
    path.length > 0 && path.length <= 4096 && !/[\u0000-\u001f\u007f]/u.test(path);
}

/**
 * Adapt a separately authenticated native scanner coordinator to the only
 * currently installed protection profile, preserving all native safety gates.
 *
 * readConfiguration must be an explicitly injected, trusted read-only
 * snapshot provider for selectedProtectionProfile (not a browser setting,
 * a page payload, or the preview-only preferredProtectionLevel).
 *
 * The underlying coordinator must enforce the second-argument policy
 * contract in its native implementation and report its actual effective
 * policy ID. This module never runs ClamAV or asserts a clean scan.
 */
export function createConfiguredDownloadProtectionCoordinator(
  trustedCoordinator, readConfiguration
) {
  const send = own(trustedCoordinator, "submitCompletedPdfDownload");
  const ready = own(trustedCoordinator, "nativeScannerReady") === true;
  if (typeof readConfiguration !== "function" || typeof send !== "function") {
    throw new TypeError("A trusted native scanner coordinator and configuration reader are required");
  }
  return Object.freeze({
    nativeScannerReady: ready,
    async submitCompletedPdfDownload(request) {
      if (!ready || own(trustedCoordinator, "nativeScannerReady") !== true ||
          !validRequest(request)) return rejected;
      try {
        // Read configuration on EVERY request, never cache a stale selection.
        const configuration = await readConfiguration();
        if (!activeSelection(configuration) ||
            own(trustedCoordinator, "nativeScannerReady") !== true) return rejected;
        // Send only the already validated path/ID to the trusted coordinator;
        // the policy is separate from the browser-originated request envelope.
        const candidate = Object.freeze({
          id: own(request, "id"), localPath: own(request, "localPath")
        });
        const result = await send.call(trustedCoordinator, candidate, policy);
        // Accepted is NOT a clean scan, and the native side must confirm the
        // effective policy it actually applied, not just echo caller metadata.
        if (own(trustedCoordinator, "nativeScannerReady") !== true ||
            own(result, "accepted") !== true ||
            own(result, "effectivePolicyId") !== POLICY_ID) return rejected;
        // A configuration change while awaiting the native response cannot
        // be treated as an accepted request under the current policy.
        if (!activeSelection(await readConfiguration())) return rejected;
        return accepted;
      } catch {
        // No browser paths, settings, or native diagnostics enter error output.
        return rejected;
      }
    }
  });
}

export const installedDownloadProtectionPolicy = policy;
