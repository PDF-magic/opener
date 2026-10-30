// Local responses for native connection failures (opener-0633).
// A broken or absent native channel cannot carry a response from the host.
// This pure module does not connect, register, grant permissions or scan PDFs.
import { createMessage } from "./messaging.js";

export const NATIVE_CONNECTION_ERROR_CODES = Object.freeze({
  HOST_UNAVAILABLE: "native-host-unavailable",
  PERMISSION_DENIED: "native-permission-denied",
  DISCONNECTED: "native-connection-disconnected",
  HANDSHAKE_FAILED: "native-handshake-failed",
  TIMEOUT: "native-connection-timeout",
  FAILED: "native-connection-failed"
});

const KNOWN_CODES = new Set(Object.values(NATIVE_CONNECTION_ERROR_CODES));

/**
 * Create a local, correlated v1 error response for a failed native connection.
 * `code` is selected by trusted connection lifecycle code, never by matching
 * browser error messages. Unknown input is a generic failure; no exception,
 * host name, native path, document data or browser diagnostics are serialized.
 * This response is for the extension caller, NOT for sending to a dead host.
 */
export function createNativeConnectionErrorResponse(requestId, code) {
  const safeCode = typeof code === "string" && KNOWN_CODES.has(code)
    ? code : NATIVE_CONNECTION_ERROR_CODES.FAILED;
  return createMessage("response", "host.connection", requestId, {
    status: "error",
    code: safeCode,
    connected: false,
    scanAvailable: false,
    scanStarted: false,
    scanVerified: false,
    authorizesOpen: false
  });
}
