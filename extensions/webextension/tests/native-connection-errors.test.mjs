import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";
import { parseMessage, serializeMessage } from "../src/messaging.js";
import {
  createNativeConnectionErrorResponse, NATIVE_CONNECTION_ERROR_CODES
} from "../src/native-connection-errors.js";

const codes = NATIVE_CONNECTION_ERROR_CODES;
const expected = (code, requestId = "connection_1") => ({
  version: 1, kind: "response", topic: "host.connection", requestId,
  payload: {
    status: "error", code, connected: false, scanAvailable: false,
    scanStarted: false, scanVerified: false, authorizesOpen: false
  }
});

test("reports every known connection failure with the versioned response format", () => {
  assert.ok(Object.isFrozen(codes));
  for (const code of Object.values(codes)) {
    const response = createNativeConnectionErrorResponse("connection_1", code);
    assert.deepEqual(response, expected(code));
    assert.deepEqual(parseMessage(serializeMessage(response)), response);
  }
});

test("correlates requests without changing other native protocol topics", () => {
  assert.deepEqual(createNativeConnectionErrorResponse("hello_2", codes.HANDSHAKE_FAILED),
    expected(codes.HANDSHAKE_FAILED, "hello_2"));
  assert.equal(createNativeConnectionErrorResponse("scan_3", codes.DISCONNECTED).topic,
    "host.connection");
});

test("unknown and raw browser errors become generic, path-free failures", () => {
  const sensitive = "/Users/private/Documents/medical.pdf";
  const inputs = [undefined, null, "", "host was missing at " + sensitive,
    new Error("Native host missing: " + sensitive),
    { get message() { throw Error("getter must not execute"); } },
    { code: codes.PERMISSION_DENIED }, 123, true];
  for (const input of inputs) {
    const response = createNativeConnectionErrorResponse("safe_1", input);
    assert.deepEqual(response, expected(codes.FAILED, "safe_1"));
    assert.equal(JSON.stringify(response).includes(sensitive), false);
  }
});

test("error responses always deny scanner and file-opening authority", () => {
  for (const code of Object.values(codes)) {
    const { payload } = createNativeConnectionErrorResponse("deny_1", code);
    for (const key of ["connected", "scanAvailable", "scanStarted",
      "scanVerified", "authorizesOpen"]) assert.equal(payload[key], false);
    for (const forbidden of ["path", "hostName", "message", "verdict", "result",
      "permissionGranted", "scanRequestId"]) assert.equal(forbidden in payload, false);
  }
});

test("invalid correlation IDs are rejected without echoing attacker data", () => {
  for (const id of ["", "bad/id", "has space", "x".repeat(81),
    null, 1, {}, new String("id")]) {
    assert.throws(() => createNativeConnectionErrorResponse(id, codes.FAILED), TypeError);
  }
});

test("responses are detached from subsequent caller mutations", () => {
  const response = createNativeConnectionErrorResponse("req_1", codes.TIMEOUT);
  response.payload.code = "tampered";
  assert.deepEqual(createNativeConnectionErrorResponse("req_1", codes.TIMEOUT),
    expected(codes.TIMEOUT, "req_1"));
});

test("error handler does not activate native messaging or any privileged action", async () => {
  const source = await readFile(new URL("../src/native-connection-errors.js", import.meta.url),
    "utf8");
  const executable = source.replace(/\/\/[^\n]*/g, "");
  for (const forbidden of ["connectNative(", "sendNativeMessage(",
    "permissions.request(", "browser.", "chrome.", "fetch(", "addListener(",
    "window.open(", "localStorage", "node:fs", "clamscan", "scan-and-open"]) {
    assert.equal(executable.includes(forbidden), false, forbidden);
  }
});
