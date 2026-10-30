import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";
import { displayVerifiedCleanDownloadScanResult as display } from "../src/download-clean-result-display.js";

const requestId = "scan_query_42";
const scanRequestId = "scan_task_42";
const context = Object.freeze({ requestId, scanRequestId });
const SUCCESS_TEXT = "Scan complete: required checks found no threats. Opening still requires separate approval.";
const UNVERIFIED_TEXT = "No verified clean scan result is available.";

function target() {
  const attrs = new Map();
  return {
    textContent: "",
    setAttribute(name, value) { attrs.set(name, value); },
    getAttribute(name) { return attrs.get(name); }
  };
}

function verifiedMessage() {
  return {
    version: 1, kind: "response", topic: "scan.result", requestId,
    payload: {
      scanRequestId, status: "complete", result: { status: "clean" },
      scanCompleted: true, scanVerified: true, authorizesOpen: false
    }
  };
}

test("renders a verified clean result in an accessible inert status element", () => {
  const view = target();
  assert.equal(display(view, verifiedMessage(), context), true);
  assert.equal(view.textContent, SUCCESS_TEXT);
  assert.equal(view.getAttribute("role"), "status");
  assert.equal(view.getAttribute("aria-live"), "polite");
  assert.equal("innerHTML" in view, false);
  assert.equal(view.textContent.includes("Opening still requires separate approval"), true);
});

test("actual transport-only scan.result unavailable response cannot appear clean", () => {
  const view = target();
  const unavailable = verifiedMessage();
  unavailable.payload = {
    scanRequestId, status: "unavailable",
    reason: "trusted-scan-coordinator-required", result: null,
    scanCompleted: false, scanVerified: false, authorizesOpen: false
  };
  assert.equal(display(view, unavailable, context), false);
  assert.equal(view.textContent, UNVERIFIED_TEXT);
});

test("submission acknowledgments and download metadata never assert a clean verdict", () => {
  const view = target();
  for (const response of [
    { accepted: true, scanVerified: true, authorizesOpen: true },
    { status: "submitted", id: 42, scanSubmitted: true, scanVerified: true },
    { kind: "completed", id: 42, danger: "safe" },
    { status: "request-submitted" },
    { scanRequestId, result: { status: "clean" } }
  ]) {
    assert.equal(display(view, response, context), false);
    assert.equal(view.textContent, UNVERIFIED_TEXT);
  }
});

test("rejects every nonclean terminal outcome and incomplete/unverified scan", () => {
  for (const status of [
    "malwareDetected", "suspiciousStructure", "encrypted", "incompleteScan",
    "scanFailed", "scanTimedOut", "fileChanged", "fileTooLarge", "cancelled",
    "Clean", "CLEAN", "warning", "unknown", ""
  ]) {
    const response = verifiedMessage();
    response.payload.result.status = status;
    const view = target();
    assert.equal(display(view, response, context), false, status);
    assert.equal(view.textContent, UNVERIFIED_TEXT);
  }
  for (const changed of [
    { status: "pending" }, { status: "unavailable" },
    { scanVerified: false }, { scanVerified: "true" },
    { scanCompleted: false }, { scanCompleted: 1 },
    { authorizesOpen: true }, { result: null },
    { result: { status: "clean", untrusted: "dangerous" } },
    { result: { status: "clean", fromCache: true } },
    { result: "clean" }
  ]) {
    const response = verifiedMessage();
    Object.assign(response.payload, changed);
    assert.equal(display(target(), response, context), false, JSON.stringify(changed));
  }
});

test("both native envelope request and scan-job identifiers must match exactly", () => {
  for (const changed of [
    { requestId: "another_request" }, { requestId: "other\nid" },
    { topic: "scan.status" }, { topic: "host.health" },
    { kind: "request" }, { version: 2 }, { version: "1" },
    { payload: { scanRequestId: "other_job" } }
  ]) {
    const response = verifiedMessage();
    if (changed.payload) Object.assign(response.payload, changed.payload);
    else Object.assign(response, changed);
    assert.equal(display(target(), response, context), false, JSON.stringify(changed));
  }
  assert.equal(display(target(), verifiedMessage(),
    { requestId: "other_request", scanRequestId }), false);
  assert.equal(display(target(), verifiedMessage(),
    { requestId, scanRequestId: "other_job" }), false);
  for (const id of ["", "a b", "a\nb", "a".repeat(81), 2, null]) {
    assert.equal(display(target(), verifiedMessage(),
      { requestId: id, scanRequestId }), false);
  }
});

test("rejects extra caller claims, symbols, inherited data and accessor properties", () => {
  for (const mutation of [
    (x) => { x.payload.localPath = "/private/report.pdf"; },
    (x) => { x.url = "https://secret.example"; },
    (x) => { x.payload[Symbol("private")] = "secret"; },
    (x) => { x.payload.result.__proto__ = { accepted: true }; },
    (x) => { Object.defineProperty(x.payload, "scanVerified", {
      get() { throw Error("should never evaluate property getter"); }
    }); },
    (x) => { Object.defineProperty(x.payload.result, "status", {
      get() { throw Error("must not execute untrusted getter"); }
    }); }
  ]) {
    const response = verifiedMessage();
    mutation(response);
    assert.equal(display(target(), response, context), false);
  }
});

test("unknown or malformed messages clear a previously displayed clean status", () => {
  const view = target();
  assert.equal(display(view, verifiedMessage(), context), true);
  assert.equal(view.textContent, SUCCESS_TEXT);
  for (const invalid of [null, undefined, [], "clean", {}, Object.create(null)]) {
    assert.equal(display(view, invalid, context), false);
    assert.equal(view.textContent, UNVERIFIED_TEXT);
    assert.equal(view.getAttribute("role"), "status");
    assert.equal(view.getAttribute("aria-live"), "polite");
  }
});

test("browser paths, URLs, scanner diagnostics and HTML never appear in output", () => {
  const view = target();
  const response = verifiedMessage();
  response.payload.result = {
    status: "clean", filename: '<img src=x onerror=alert(1)>',
    url: "https://private.example/?token=secret", error: "/private/path.pdf"
  };
  assert.equal(display(view, response, context), false);
  assert.equal(view.textContent, UNVERIFIED_TEXT);
  for (const secret of ["private", "http", "<img", "onerror", "token", "secret"]) {
    assert.equal(view.textContent.includes(secret), false);
  }
});

test("frozen native payloads may be safely displayed without mutation", () => {
  const payload = verifiedMessage();
  Object.freeze(payload.payload.result);
  Object.freeze(payload.payload);
  Object.freeze(payload);
  const view = target();
  assert.equal(display(view, payload, context), true);
  assert.equal(view.textContent, SUCCESS_TEXT);
});

test("missing DOM or hostile target fails without leaking sensitive response details", () => {
  assert.equal(display(null, verifiedMessage(), context), false);
  assert.equal(display({}, verifiedMessage(), context), false);
  const broken = { setAttribute() { throw Error("/private/report.pdf"); } };
  assert.equal(display(broken, verifiedMessage(), context), false);
  const noText = {
    setAttribute() {},
    set textContent(value) { throw Error(value + "/private/report.pdf"); }
  };
  assert.equal(display(noText, verifiedMessage(), context), false);
});

test("readiness flags and legacy native host messages cannot bypass validation", () => {
  const message = verifiedMessage();
  message.payload.result = { status: "clean", scanVerified: true };
  message.payload.scanAvailable = true;
  assert.equal(display(target(), message, context), false);
  const noContext = display(target(), verifiedMessage());
  assert.equal(noContext, false);
});

test("presentation module is passive; neither popup nor scanner becomes active", async () => {
  const source = await readFile(new URL("../src/download-clean-result-display.js", import.meta.url), "utf8");
  const background = await readFile(new URL("../src/background.js", import.meta.url), "utf8");
  const popup = await readFile(new URL("../src/popup.html", import.meta.url), "utf8");
  assert.equal(background.trimEnd().endsWith("void 0;"), true);
  assert.match(popup, /Not active/);
  assert.match(popup, /disabled aria-disabled="true"/);
  assert.equal(source.includes(".textContent ="), true);
  for (const forbidden of [
    "innerHTML", "connectNative(", "sendNativeMessage(", "scan_and_open",
    "clamscan", "node:fs", "fetch(", "localStorage", "storage.local",
    "downloads.open(", "permissions.request(", "window.open("
  ]) assert.equal(source.includes(forbidden), false, forbidden);
});
