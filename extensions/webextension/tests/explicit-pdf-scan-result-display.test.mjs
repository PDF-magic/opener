import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";
import {
  createExplicitPdfScanResultDisplay as createDisplay, EMPTY_EXPLICIT_SCAN_RESULT
} from "../src/explicit-pdf-scan-result-display.js";
import { validatePopupAsset } from "../scripts/popup-assets.mjs";

const ids = { requestId: "request_7", scanRequestId: "scan_7", selectionId: "pdf_7" };
function element() {
  const attrs = new Map();
  return { id: "explicitPdfScanResult", nodeType: 1, textContent: "", attrs,
    setAttribute(name, value) { attrs.set(name, value); } };
}
function message(status = "clean", patch = {}) {
  return { version: 1, kind: "response", topic: "scan.result", requestId: ids.requestId,
    payload: { scanRequestId: ids.scanRequestId, status: "complete",
      result: { status }, scanCompleted: true, scanVerified: true,
      authorizesOpen: false, ...patch } };
}
function fixture(reply = message()) {
  const target = element(), calls = [];
  const coordinator = { nativeScanResultsReady: true, selected: ids.selectionId,
    readCurrentSelectionId() { return this.selected; },
    readVerifiedExplicitPdfScanResult: async (context) => {
      calls.push(context); return reply;
    } };
  return { target, coordinator, calls, display: createDisplay(target, coordinator) };
}

test("popup contains exactly one accessible Scan result placeholder and stays inactive", async () => {
  const html = await readFile(new URL("../src/popup.html", import.meta.url), "utf8");
  const css = await readFile(new URL("../src/popup.css", import.meta.url), "utf8");
  const section = '<section class="scan-result" aria-labelledby="explicit-pdf-result-title">';
  const title = '<h2 id="explicit-pdf-result-title">Scan result</h2>';
  const placeholder = '<p id="explicitPdfScanResult" role="status" aria-live="polite">No verified scan result is available.</p>';
  assert.doesNotThrow(() => validatePopupAsset("popup.html", html));
  for (const part of [section, title, placeholder]) assert.equal(html.split(part).length, 2);
  assert.match(css, /\.scan-result\b/);
  assert.match(html, /Not active/);
  assert.match(html, /id="scanThisPDF" type="button" disabled aria-disabled="true"/);
  for (const mutated of [
    html.replace(placeholder, ""),
    html.replace(placeholder, placeholder + placeholder),
    html.replace(placeholder, placeholder.replace('role="status"', 'role="alert"')),
    html.replace(placeholder, placeholder.replace("No verified scan result is available.", "Scan clean")),
    html.replace(title, "")
  ]) assert.throws(() => validatePopupAsset("popup.html", mutated));
});

test("without a verified native coordinator the result remains explicitly unknown", async () => {
  const target = element();
  const display = createDisplay(target);
  assert.equal(target.textContent, EMPTY_EXPLICIT_SCAN_RESULT);
  assert.deepEqual(await display.show(ids), {
    status: "unavailable", displayed: false, scanVerified: false, authorizesOpen: false
  });
  assert.equal(target.attrs.get("role"), "status");
});

test("only correlated completed verified clean results render a non-opening success", async () => {
  const f = fixture();
  const result = await f.display.show(ids);
  assert.deepEqual(f.calls, [ids]);
  assert.deepEqual(result, {
    status: "clean", displayed: true, scanVerified: true, authorizesOpen: false
  });
  assert.equal(Object.isFrozen(result), true);
  assert.match(f.target.textContent, /no threats/);
  assert.match(f.target.textContent, /Opening still requires separate approval/);
  assert.equal(f.target.attrs.get("role"), "status");
  assert.equal(f.target.attrs.get("aria-live"), "polite");
});

test("verified malware is an assertive blocking alert, not open authorization", async () => {
  const f = fixture(message("malwareDetected"));
  const result = await f.display.show(ids);
  assert.equal(result.status, "malwareDetected");
  assert.equal(result.authorizesOpen, false);
  assert.match(f.target.textContent, /Malware detected/);
  assert.equal(f.target.attrs.get("role"), "alert");
  assert.equal(f.target.attrs.get("aria-live"), "assertive");
});

test("known blocked or failed outcomes show a generic warning, never clean", async () => {
  for (const status of ["suspiciousStructure", "encrypted", "fileTooLarge",
    "fileChanged", "scanFailed", "incompleteScan", "scanTimedOut", "cancelled"]) {
    const f = fixture(message(status));
    const result = await f.display.show(ids);
    assert.equal(result.status, "blocked", status);
    assert.equal(result.scanVerified, false);
    assert.match(f.target.textContent, /Do not open/);
    assert.equal(f.target.attrs.get("role"), "alert");
  }
  const f = fixture(message("scanFailed", {
    status: "failed", scanCompleted: false, scanVerified: false
  }));
  assert.equal((await f.display.show(ids)).status, "blocked");
});

test("spoofed, unverified, mismatched or unavailable messages never render results", async () => {
  for (const invalid of [
    { status: "submitted", scanVerified: true },
    { kind: "completed", id: 4 },
    message("clean", { scanVerified: false }),
    message("clean", { scanCompleted: false }),
    message("clean", { authorizesOpen: true }),
    message("malwareDetected", { scanVerified: false }),
    message("clean", { extra: true }),
    { ...message(), topic: "scan.progress" },
    { ...message(), requestId: "another" },
    { ...message(), payload: { ...message().payload, scanRequestId: "different" } },
    { ...message(), payload: { ...message().payload, result: { status: "clean", path: "/private.pdf" } } },
    { ...message(), payload: { ...message().payload, status: "unavailable",
      reason: "trusted-scan-coordinator-required", scanCompleted: false,
      scanVerified: false, result: null } }
  ]) {
    const f = fixture(invalid);
    assert.equal((await f.display.show(ids)).status, "unavailable");
    assert.equal(f.target.textContent, EMPTY_EXPLICIT_SCAN_RESULT);
    assert.equal(f.target.attrs.get("role"), "status");
  }
});

test("rejects accessors, proxies, inherited claims and private text", async () => {
  const getter = message();
  Object.defineProperty(getter.payload.result, "status", {
    get() { throw Error("/private/secret.pdf"); }
  });
  for (const candidate of [
    getter, new Proxy({}, { ownKeys() { throw Error("secret"); } }),
    { ...message(), url: "https://private.example/" },
    { ...message(), payload: { ...message().payload, [Symbol("secret")]: true } },
    Object.create(message())
  ]) {
    const f = fixture(candidate);
    assert.equal((await f.display.show(ids)).status, "unavailable");
    assert.doesNotMatch(f.target.textContent, /private|secret|https/i);
  }
});

test("selection and coordinator must remain trusted across asynchronous reads", async () => {
  const f = fixture();
  f.coordinator.selected = "other";
  assert.equal((await f.display.show(ids)).status, "unavailable");
  assert.deepEqual(f.calls, []);
  f.coordinator.selected = ids.selectionId;
  let deliver;
  f.coordinator.readVerifiedExplicitPdfScanResult = () =>
    new Promise(resolve => { deliver = resolve; });
  const pending = f.display.show(ids);
  f.coordinator.selected = "other";
  deliver(message());
  assert.equal((await pending).status, "unavailable");
  assert.equal(f.target.textContent, EMPTY_EXPLICIT_SCAN_RESULT);
});

test("clear, invalid updates and disposal invalidate prior successful results", async () => {
  const f = fixture();
  assert.equal((await f.display.show(ids)).status, "clean");
  assert.equal((await f.display.show({ ...ids, scanRequestId: "wrong" })).status, "unavailable");
  assert.equal(f.target.textContent, EMPTY_EXPLICIT_SCAN_RESULT);
  let deliver;
  f.coordinator.readVerifiedExplicitPdfScanResult = () =>
    new Promise(resolve => { deliver = resolve; });
  const pending = f.display.show(ids);
  f.display.clear();
  deliver(message());
  assert.equal((await pending).status, "unavailable");
  assert.equal(f.target.textContent, EMPTY_EXPLICIT_SCAN_RESULT);
  f.display.dispose();
  assert.equal((await f.display.show(ids)).status, "unavailable");
});

test("invalid targets, malformed IDs, native failures and inactive extension fail closed", async () => {
  assert.throws(() => createDisplay(null), TypeError);
  assert.throws(() => createDisplay({}), TypeError);
  const f = fixture();
  for (const bad of [{ ...ids, requestId: 1 }, { ...ids, selectionId: "/private" },
    { ...ids, scanRequestId: "x".repeat(81) }, {}]) {
    assert.equal((await f.display.show(bad)).status, "unavailable");
  }
  f.coordinator.readVerifiedExplicitPdfScanResult = async () => {
    throw Error("/private/secret.pdf");
  };
  assert.equal((await f.display.show(ids)).status, "unavailable");
  const source = await readFile(new URL("../src/explicit-pdf-scan-result-display.js", import.meta.url), "utf8");
  const worker = await readFile(new URL("../src/background.js", import.meta.url), "utf8");
  const manifest = JSON.parse(await readFile(new URL("../manifest.json", import.meta.url), "utf8"));
  const ci = await readFile(new URL("../../../.github/workflows/ci.yml", import.meta.url), "utf8");
  assert.deepEqual(manifest.permissions, []);
  assert.deepEqual(manifest.host_permissions, []);
  assert.ok(worker.trimEnd().endsWith("void 0;"));
  assert.match(ci, /node --test tests\/explicit-pdf-scan-result-display\.test\.mjs/);
  for (const forbidden of ["innerHTML", "fetch(", "chrome.", "browser.", "globalThis.",
    "sendNativeMessage(", "connectNative(", "downloads.open(", "permissions.request(", "localStorage"]) {
    assert.equal(source.includes(forbidden), false, forbidden);
  }
});
