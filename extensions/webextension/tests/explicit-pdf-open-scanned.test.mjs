import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";
import { createDownloadOpenCommandGate } from "../src/download-open-command-once.js";
import { createOpenScannedPdfAction, OPEN_SCANNED_PDF_LABEL } from "../src/explicit-pdf-open-scanned.js";

const ids = { requestId: "ui_12", scanRequestId: "scan_12", selectionId: "pdf_12" };
const result = status => ({
  status, enabled: status === "offered", scanVerified: false,
  authorizesOpen: false, opened: false
});
function scan(status = "clean") {
  return {
    version: 1, kind: "response", topic: "scan.result", requestId: ids.requestId,
    payload: {
      scanRequestId: ids.scanRequestId, status: "complete",
      scanCompleted: true, scanVerified: true, authorizesOpen: false,
      result: { status }
    }
  };
}
function element(tag = "div", doc = null) {
  const callbacks = new Map();
  return {
    tagName: tag, nodeType: 1, ownerDocument: doc, hidden: false,
    disabled: false, type: null, textContent: "", children: [],
    attributes: new Map(),
    replaceChildren(...items) { this.children = items; },
    setAttribute(name, value) { this.attributes.set(name, value); },
    addEventListener(event, callback) {
      if (!callbacks.has(event)) callbacks.set(event, new Set());
      callbacks.get(event).add(callback);
    },
    removeEventListener(event, callback) { callbacks.get(event)?.delete(callback); },
    fire(event, payload = { isTrusted: true }) {
      return Promise.all([...callbacks.get(event) ?? []].map(fn => fn(payload)));
    },
    get listenerCount() {
      return [...callbacks.values()].reduce((n, set) => n + set.size, 0);
    }
  };
}
function root() {
  const doc = { createElement(name) { return element(name, doc); } };
  return element("section", doc);
}
function fixture() {
  const reads = [], opens = [];
  const coordinator = {
    nativeScanResultsReady: true, nativeVerifiedOpeningReady: true,
    readCurrentSelectionId: () => ids.selectionId,
    readVerifiedExplicitPdfScanResult(ref) {
      reads.push(ref);
      return Promise.resolve(scan());
    },
    requestVerifiedExplicitPdfOpen(ref) {
      opens.push(ref);
      return Promise.resolve({ accepted: true, scanRequestId: ids.scanRequestId });
    }
  };
  const gate = createDownloadOpenCommandGate();
  const target = root();
  const action = createOpenScannedPdfAction(target, coordinator, gate);
  return { reads, opens, coordinator, gate, target, action };
}
function teardown(f) { f.action.dispose(); f.gate.dispose(); }
const tick = () => new Promise(resolve => setImmediate(resolve));

test("an independently verified clean explicit scan offers an accessible action", async () => {
  const f = fixture();
  assert.deepEqual(f.action.state(), result("unavailable"));
  assert.equal(f.target.hidden, true);
  assert.deepEqual(await f.action.offer(ids), result("offered"));
  assert.equal(f.target.hidden, false);
  assert.equal(f.target.children[0].textContent, OPEN_SCANNED_PDF_LABEL);
  assert.equal(f.target.children[0].type, "button");
  assert.equal(f.target.children[1].attributes.get("role"), "status");
  assert.equal(f.target.children[1].attributes.get("aria-live"), "polite");
  assert.match(f.target.children[1].textContent, /quarantine/);
  assert.deepEqual(f.opens, []);
  assert.ok(Object.isFrozen(f.action));
  assert.ok(Object.isFrozen(f.action.state()));
  teardown(f);
});

test("trusted click rechecks clean scan and sends only opaque scan ID", async () => {
  const f = fixture();
  await f.action.offer(ids);
  await f.target.children[0].fire("click", { isTrusted: true });
  assert.deepEqual(f.opens, [{ scanRequestId: ids.scanRequestId }]);
  assert.ok(Object.isFrozen(f.opens[0]));
  assert.equal(f.reads.length, 2);
  assert.ok(Object.isFrozen(f.reads[0]));
  assert.deepEqual(f.action.state(), result("request-submitted"));
  assert.match(f.target.children[1].textContent, /Native safety checks/);
  assert.equal(f.target.children[0].disabled, true);
  teardown(f);
});

test("synthetic clicks and background interactions never submit an open", async () => {
  const f = fixture();
  await f.action.offer(ids);
  for (const event of [{ isTrusted: false }, { isTrusted: "true" }, {}, null]) {
    await f.target.children[0].fire("click", event);
  }
  await f.target.children[0].fire("mouseover", { isTrusted: true });
  assert.equal(f.opens.length, 0);
  assert.deepEqual(f.action.state(), result("offered"));
  teardown(f);
});

test("malware, failure and incomplete or claimed browser clean metadata never offer an action", async () => {
  const invalid = [
    scan("malwareDetected"), scan("blocked"), scan("suspiciousStructure"),
    { ...scan(), payload: { ...scan().payload, scanCompleted: false } },
    { ...scan(), payload: { ...scan().payload, scanVerified: false } },
    { ...scan(), payload: { ...scan().payload, authorizesOpen: true } },
    { ...scan(), payload: { ...scan().payload, result: { status: "clean", path: "/secret.pdf" } } },
    { ...scan(), requestId: "another" },
    { ...scan(), kind: "request" },
    { status: "clean", accepted: true }, null
  ];
  for (const message of invalid) {
    const f = fixture();
    f.coordinator.readVerifiedExplicitPdfScanResult = async () => message;
    assert.deepEqual(await f.action.offer(ids), result("unavailable"));
    assert.equal(f.target.hidden, true);
    assert.deepEqual(f.opens, []);
    teardown(f);
  }
});

test("missing coordinator, revoked permissions and stale selection deny the control", async () => {
  for (const key of [
    "nativeScanResultsReady", "nativeVerifiedOpeningReady",
    "readCurrentSelectionId", "readVerifiedExplicitPdfScanResult",
    "requestVerifiedExplicitPdfOpen"
  ]) {
    const f = fixture();
    f.coordinator[key] = undefined;
    assert.deepEqual(await f.action.offer(ids), result("unavailable"), key);
    teardown(f);
  }
  const f = fixture();
  f.coordinator.readCurrentSelectionId = () => "other_pdf";
  assert.deepEqual(await f.action.offer(ids), result("unavailable"));
  teardown(f);
});

test("invalid request IDs and inherited or accessor scan reports fail closed", async () => {
  for (const value of [
    { ...ids, requestId: "../secret" }, { ...ids, scanRequestId: "" },
    { ...ids, selectionId: "x".repeat(81) }, { ...ids, requestId: 5 }
  ]) {
    const f = fixture();
    assert.deepEqual(await f.action.offer(value), result("unavailable"));
    teardown(f);
  }
  for (const value of [
    Object.assign(Object.create(scan()), {}),
    { ...scan(), payload: { ...scan().payload, get scanVerified() { throw Error("/private/file.pdf"); } } },
    new Proxy({}, { ownKeys() { throw Error("secret"); } })
  ]) {
    const f = fixture();
    f.coordinator.readVerifiedExplicitPdfScanResult = async () => value;
    assert.deepEqual(await f.action.offer(ids), result("unavailable"));
    teardown(f);
  }
});

test("button becomes ineligible when scan result changes before the trusted click", async () => {
  const f = fixture();
  await f.action.offer(ids);
  f.coordinator.readVerifiedExplicitPdfScanResult = async () => scan("malwareDetected");
  await f.target.children[0].fire("click", { isTrusted: true });
  assert.deepEqual(f.opens, []);
  assert.deepEqual(f.action.state(), result("unavailable"));
  teardown(f);
});

test("a clean result revoked during asynchronous recheck cannot dispatch", async () => {
  const f = fixture();
  let release;
  let count = 0;
  f.coordinator.readVerifiedExplicitPdfScanResult = () => {
    count++;
    return count === 1 ? Promise.resolve(scan()) :
      new Promise(resolve => { release = resolve; });
  };
  await f.action.offer(ids);
  const pending = f.target.children[0].fire("click", { isTrusted: true });
  f.coordinator.readCurrentSelectionId = () => "new_pdf";
  release(scan());
  await pending;
  assert.deepEqual(f.opens, []);
  assert.deepEqual(f.action.state(), result("unavailable"));
  teardown(f);
});

test("opening request is one-shot across repeated trusted clicks and separate UI views", async () => {
  const f = fixture();
  let release;
  f.coordinator.requestVerifiedExplicitPdfOpen = req => {
    f.opens.push(req);
    return new Promise(resolve => { release = resolve; });
  };
  await f.action.offer(ids);
  const second = createOpenScannedPdfAction(root(), f.coordinator, f.gate);
  await second.offer(ids);
  const pending = f.target.children[0].fire("click", { isTrusted: true });
  await tick();
  assert.equal(f.opens.length, 1);
  await f.target.children[0].fire("click", { isTrusted: true });
  assert.equal(f.opens.length, 1);
  await second.offer(ids);
  assert.deepEqual(second.state(), result("offered"));
  await second.offer(ids);
  const view = second;
  // A second view must not bypass the session-owned one-shot opening gate.
  release({ accepted: true, scanRequestId: ids.scanRequestId });
  await pending;
  assert.deepEqual(f.action.state(), result("request-submitted"));
  await f.action.offer(ids);
  await f.target.children[0].fire("click", { isTrusted: true });
  assert.equal(f.opens.length, 1);
  view.dispose();
  teardown(f);
});

test("malformed acknowledgement or native errors never claim PDF opened", async () => {
  for (const response of [
    { accepted: false, scanRequestId: ids.scanRequestId },
    { accepted: "true", scanRequestId: ids.scanRequestId },
    { accepted: true, scanRequestId: "other" },
    { accepted: true, scanRequestId: ids.scanRequestId, opened: true },
    null, { opened: true }
  ]) {
    const f = fixture();
    f.coordinator.requestVerifiedExplicitPdfOpen = async () => response;
    await f.action.offer(ids);
    await f.target.children[0].fire("click", { isTrusted: true });
    assert.deepEqual(f.action.state(), result("unavailable"));
    assert.equal(f.action.state().opened, false);
    teardown(f);
  }
  const f = fixture();
  f.coordinator.requestVerifiedExplicitPdfOpen = () => {
    throw Error("/private/secret.pdf");
  };
  await f.action.offer(ids);
  await f.target.children[0].fire("click", { isTrusted: true });
  assert.deepEqual(f.action.state(), result("unavailable"));
  assert.doesNotMatch(JSON.stringify(f.action.state()), /private|secret/);
  teardown(f);
});

test("clearing or switching selection invalidates late scan results", async () => {
  const f = fixture();
  let resolve;
  f.coordinator.readVerifiedExplicitPdfScanResult = () =>
    new Promise(done => { resolve = done; });
  const pending = f.action.offer(ids);
  f.action.clear();
  resolve(scan());
  assert.deepEqual(await pending, result("unavailable"));
  assert.equal(f.target.hidden, true);
  teardown(f);
});

test("disposing prevents stale native acknowledgements from changing UI", async () => {
  const f = fixture();
  let resolve;
  f.coordinator.requestVerifiedExplicitPdfOpen = () =>
    new Promise(done => { resolve = done; });
  await f.action.offer(ids);
  const button = f.target.children[0];
  const pending = button.fire("click", { isTrusted: true });
  await tick();
  f.action.dispose();
  assert.equal(button.listenerCount, 0);
  resolve({ accepted: true, scanRequestId: ids.scanRequestId });
  await pending;
  assert.deepEqual(f.action.state(), result("unavailable"));
  assert.equal(f.target.hidden, true);
  assert.deepEqual(await f.action.offer(ids), result("unavailable"));
  f.gate.dispose();
});

test("inactive extension and scanner settings stay unchanged, without opening side effects", async () => {
  assert.throws(() => createOpenScannedPdfAction({}, null, null), TypeError);
  const code = await readFile(new URL("../src/explicit-pdf-open-scanned.js", import.meta.url), "utf8");
  const worker = await readFile(new URL("../src/background.js", import.meta.url), "utf8");
  const manifest = JSON.parse(await readFile(new URL("../manifest.json", import.meta.url), "utf8"));
  assert.equal(worker.trimEnd().endsWith("void 0;"), true);
  assert.deepEqual(manifest.permissions, []);
  assert.deepEqual(manifest.host_permissions, []);
  for (const forbidden of [
    "innerHTML", "sendNativeMessage(", "connectNative(", "window.open(",
    "downloads.open(", "node:fs", "fetch(", "permissions.request(",
    "localStorage", "clamscan"
  ]) assert.equal(code.includes(forbidden), false, forbidden);
});
