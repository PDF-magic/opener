import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";
import { createNativeConnectionErrorResponse, NATIVE_CONNECTION_ERROR_CODES } from
  "../src/native-connection-errors.js";
import { createDownloadScannerUnavailableDisplay as createDisplay } from
  "../src/download-scanner-unavailable-display.js";

function element(tagName, ownerDocument) {
  return {
    tagName, nodeType: 1, ownerDocument, hidden: false, children: [],
    textContent: "", attributes: new Map(),
    replaceChildren(...items) { this.children = items; },
    setAttribute(name, value) { this.attributes.set(name, value); },
    removeAttribute(name) { this.attributes.delete(name); }
  };
}
function fixture() {
  const doc = { createElement(tag) { return element(tag, doc); } };
  const root = element("section", doc);
  const display = createDisplay(root);
  return { root, display };
}
const expectedUnavailable = {
  status: "unavailable", scannerUnavailable: false,
  scanVerified: false, authorizesOpen: false
};
const expectedDisplayed = {
  status: "displayed", scannerUnavailable: true,
  scanVerified: false, authorizesOpen: false
};
function textOf(root) {
  return root.children.map(n => n.textContent).join(" ");
}
function reply(topic, requestId, payload) {
  return { version: 1, kind: "response", topic, requestId, payload };
}
function statusPayload() {
  return {
    scanRequestId: "scan_7", status: "unavailable",
    reason: "trusted-scan-coordinator-required",
    scanAvailable: false, scanStarted: false,
    scanVerified: false, authorizesOpen: false
  };
}
function requestPayload() {
  const { scanRequestId, ...payload } = statusPayload();
  return payload;
}
function resultPayload() {
  return {
    scanRequestId: "scan_7", status: "unavailable",
    reason: "trusted-scan-coordinator-required", result: null,
    scanCompleted: false, scanVerified: false, authorizesOpen: false
  };
}

test("show a fixed, accessible scanner-unavailable alert for native scan.status", () => {
  const f = fixture();
  assert.equal(f.root.hidden, true);
  const result = f.display.show(reply("scan.status", "status_7", statusPayload()),
    { requestId: "status_7", scanRequestId: "scan_7" });
  assert.deepEqual(result, expectedDisplayed);
  assert.ok(Object.isFrozen(result));
  assert.equal(f.root.hidden, false);
  assert.equal(f.root.attributes.get("role"), "alert");
  assert.equal(f.root.attributes.get("aria-live"), "assertive");
  assert.deepEqual(f.root.children.map(x => x.tagName), ["strong", "p"]);
  assert.match(textOf(f.root), /Scanner unavailable.*PDF not scanned/);
  assert.match(textOf(f.root), /must not be opened/);
  assert.equal(f.root.innerHTML, undefined);
});

test("scan.request unavailable and scan.result unavailable are distinguished from verdicts", () => {
  const f = fixture();
  assert.deepEqual(f.display.show(reply("scan.request", "scan_7", requestPayload()),
    { requestId: "scan_7" }), expectedDisplayed);
  assert.deepEqual(f.display.show(reply("scan.result", "result_7", resultPayload()),
    { requestId: "result_7", scanRequestId: "scan_7" }), expectedDisplayed);
  assert.equal(f.root.hidden, false);
});

test("all sanitized native connection errors can display the same safe warning", () => {
  const f = fixture();
  for (const code of Object.values(NATIVE_CONNECTION_ERROR_CODES)) {
    const message = createNativeConnectionErrorResponse("connect_7", code);
    assert.deepEqual(f.display.show(message, { requestId: "connect_7" }),
      expectedDisplayed);
    assert.doesNotMatch(textOf(f.root), /native-connection|permission-denied|\/Users/);
  }
});

test("a trusted local missing-scanner check can display without pretending a host replied", () => {
  const f = fixture();
  assert.deepEqual(f.display.showLocalUnavailable(), expectedDisplayed);
  assert.equal(f.root.hidden, false);
  assert.match(textOf(f.root), /not scanned/);
  assert.equal(f.display.showLocalUnavailable().authorizesOpen, false);
});

test("unknown statuses, extra fields and forged success or malware results cannot show an error", () => {
  const f = fixture();
  const standard = statusPayload();
  for (const payload of [
    { ...standard, status: "clean" },
    { ...standard, status: "complete" },
    { ...standard, scanVerified: true },
    { ...standard, authorizesOpen: true },
    { ...standard, scanStarted: true },
    { ...standard, scanAvailable: true },
    { ...standard, reason: "/private/secret.pdf" },
    { ...standard, localPath: "/private/secret.pdf" },
    { ...standard, diagnostic: "Host crashed" },
    { ...standard, result: "clean" }
  ]) {
    assert.deepEqual(f.display.show(reply("scan.status", "status_7", payload),
      { requestId: "status_7", scanRequestId: "scan_7" }), expectedUnavailable);
    assert.equal(f.root.hidden, true);
  }
});

test("both response ID and scan ID must match their independently expected identities", () => {
  const f = fixture();
  const msg = reply("scan.status", "status_7", statusPayload());
  for (const expected of [
    {}, { requestId: "status_8", scanRequestId: "scan_7" },
    { requestId: "status_7", scanRequestId: "scan_8" },
    { requestId: "status/7", scanRequestId: "scan_7" },
    { requestId: "status_7", scanRequestId: "scan/7" },
    { requestId: "status_7", scanRequestId: "" }
  ]) {
    assert.deepEqual(f.display.show(msg, expected), expectedUnavailable);
  }
  assert.deepEqual(f.display.show(msg, { requestId: "status_7", scanRequestId: "scan_7" }),
    expectedDisplayed);
});

test("invalid native envelope and unknown host codes are denied", () => {
  const f = fixture();
  const valid = reply("scan.status", "status_7", statusPayload());
  const connection = createNativeConnectionErrorResponse(
    "connect_7", NATIVE_CONNECTION_ERROR_CODES.HOST_UNAVAILABLE);
  for (const msg of [
    { ...valid, version: 2 }, { ...valid, kind: "event" },
    { ...valid, topic: "scan.progress" }, { ...valid, message: "private" },
    { ...valid, requestId: "status/7" }, null, [], "error",
    { ...connection, payload: { ...connection.payload, code: "/private/host" } },
    { ...connection, payload: { ...connection.payload, authorizesOpen: true } },
    { ...connection, payload: { ...connection.payload, scannerPath: "/private" } }
  ]) {
    assert.deepEqual(f.display.show(msg, { requestId: "status_7",
      scanRequestId: "scan_7" }), expectedUnavailable);
    assert.equal(f.root.hidden, true);
  }
});

test("scan.result never treats a fabricated completion, clean or null-free result as unavailable", () => {
  const f = fixture();
  const p = resultPayload();
  for (const payload of [
    { ...p, scanCompleted: true }, { ...p, scanVerified: true },
    { ...p, result: { status: "clean" } }, { ...p, status: "complete" },
    { ...p, reason: "scanFailed" }, { ...p, filename: "/private/a.pdf" }
  ]) assert.deepEqual(f.display.show(reply("scan.result", "result_7", payload),
    { requestId: "result_7", scanRequestId: "scan_7" }), expectedUnavailable);
});

test("a malformed or accessor-backed payload never runs property getters", () => {
  const f = fixture();
  let reads = 0;
  const malicious = statusPayload();
  Object.defineProperty(malicious, "status", {
    get() { reads++; throw Error("/secret/test.pdf"); }, enumerable: true
  });
  for (const data of [
    malicious,
    Object.assign(Object.create({ status: "unavailable" }), statusPayload()),
    new Proxy({}, { ownKeys() { throw Error("/secret/native-host"); } })
  ]) assert.deepEqual(f.display.show(reply("scan.status", "status_7", data),
    { requestId: "status_7", scanRequestId: "scan_7" }), expectedUnavailable);
  assert.equal(reads, 0);
});

test("error messages never copy host diagnostics, paths or attacker-supplied HTML", () => {
  const f = fixture();
  const data = statusPayload();
  data.reason = "<script>alert('/private/scan.pdf')</script>";
  assert.deepEqual(f.display.show(reply("scan.status", "status_7", data),
    { requestId: "status_7", scanRequestId: "scan_7" }), expectedUnavailable);
  f.display.showLocalUnavailable();
  assert.doesNotMatch(textOf(f.root), /<script>|private|diagnostic|clean scan/i);
});

test("clear and dispose remove stale alerts and prevent later rendering", () => {
  const f = fixture();
  f.display.showLocalUnavailable();
  f.display.clear();
  assert.equal(f.root.hidden, true);
  assert.deepEqual(f.root.children, []);
  assert.equal(f.root.attributes.has("role"), false);
  f.display.showLocalUnavailable();
  f.display.dispose();
  f.display.dispose();
  assert.equal(f.root.hidden, true);
  assert.deepEqual(f.display.showLocalUnavailable(), expectedUnavailable);
  assert.deepEqual(f.display.show(reply("scan.status", "status_7", statusPayload()),
    { requestId: "status_7", scanRequestId: "scan_7" }), expectedUnavailable);
  assert.ok(Object.isFrozen(f.display));
});

test("later unrelated native messages clear an earlier unavailable warning", () => {
  const f = fixture();
  f.display.show(reply("scan.request", "scan_7", requestPayload()),
    { requestId: "scan_7" });
  assert.equal(f.root.hidden, false);
  assert.deepEqual(f.display.show(reply("scan.status", "status_7",
    { ...statusPayload(), status: "running" }),
    { requestId: "status_7", scanRequestId: "scan_7" }), expectedUnavailable);
  assert.equal(f.root.hidden, true);
  assert.deepEqual(f.root.children, []);
});

test("presentation has no browser/native/file access or active popup listeners", async () => {
  assert.throws(() => createDisplay(null), TypeError);
  assert.throws(() => createDisplay({}), TypeError);
  const source = await readFile(
    new URL("../src/download-scanner-unavailable-display.js", import.meta.url), "utf8");
  for (const forbidden of [
    "innerHTML", "document.write", "connectNative(", "sendNativeMessage(",
    "downloads.open(", "browser.", "chrome.", "fetch(", "node:fs", "clamscan",
    "scan-and-open", "permissions.request(", "addListener(", "storage.local"
  ]) assert.equal(source.includes(forbidden), false, forbidden);
  const background = await readFile(new URL("../src/background.js", import.meta.url), "utf8");
  assert.equal(background.trimEnd().endsWith("void 0;"), true);
});
