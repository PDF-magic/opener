import { preflightCompletedDownloadForScan } from "./download-scan-preflight.js";
import { retrieveCompletedDownloadLocalPath } from "./download-local-path.js";

// Correlation is untrusted browser metadata, not an authorization to scan.
// Production extension background and native messaging remain inactive.
/**
 * Build a transient download-to-scan *candidate*, never dispatch a scan.
 *
 * The browser download ID is preserved as a decimal string compatible with
 * the existing native --browser-download-id / ScanRequest receiving field.
 * Both asynchronous, permission-checked lookups must agree on the same
 * completed download. The stronger transfer preflight runs LAST, so a stale
 * earlier path lookup cannot substitute for a current completion check.
 *
 * The returned browser path remains untrusted. A future user-authorized
 * native coordinator must independently validate canonical file identity,
 * local stability, and scanner policy immediately before any scan. No
 * browser-provided metadata is evidence of scan success or permission to open.
 */
export async function associateDownloadIdentifierWithScanCandidate(
  downloadsApi, permissionsApi, completion
) {
  try {
    // This lookup validates the exact ID-only completion notice, current
    // optional downloads permission and local path, with revocation handling.
    const local = await retrieveCompletedDownloadLocalPath(
      downloadsApi, permissionsApi, completion
    );
    if (local === null) return null;

    // Perform a fresh, stricter completion check after path retrieval.
    // Never accept a different/reused ID or partially written transfer.
    const checked = await preflightCompletedDownloadForScan(
      downloadsApi, permissionsApi, completion
    );
    if (!checked || checked.transferComplete !== true ||
        checked.scanVerified !== false || checked.authorizesScan !== false ||
        checked.authorizesOpen !== false || local.id !== checked.id ||
        !Number.isSafeInteger(checked.id) || checked.id < 0) return null;

    // This is a candidate (not a native request): callers may not treat it
    // as scanner permission, and no browser URL or other metadata is kept.
    return Object.freeze({
      kind: "browser-download-scan-candidate",
      downloadId: checked.id,
      browserDownloadIdentifier: String(checked.id),
      path: local.localPath,
      transferComplete: true,
      scanVerified: false,
      authorizesScan: false,
      authorizesOpen: false
    });
  } catch {
    // Browser failures can embed private paths and URLs: no logs or echoes.
    return null;
  }
}
