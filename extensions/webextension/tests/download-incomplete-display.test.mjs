import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";
import {
  createDownloadIncompleteScanDisplay as createDisplay
} from "../src/download-incomplete-display.js";

function element(tagName = "div", ownerDocument = null) {
  return {
    tagName, nodeType: 1, ownerDocument, hidden: false,
    children: [], textContent: "", attributes: new Map(),
    replaceChildren(...nodes) { this.children = nodes; this.textContent = ""; },
    setAttribute(name, value) { this.attributes.set(name, value); },
    removeAttribute(name) { this.attributes.delete(name); }
  };
}

function root() {
  const doc = { createElement(tagName) { return element(tagName, doc); } };
  return element("section", doc);
}

function words(node) {
  return [node.textContent, ...node.children.map(words)].filter(Boolean).join(" ");
}

function nativeResult({
  id = "scan_7", status = "incompleteScan", block = true, open = false,
  policy = "built-in", schema = 1, names = []
} = {}) {
  return {
    scanRequestId: id,
    report: {
      schemaVersion: schema, authorizesOpen: open, requiresBlock: block,
      scan: { status },
      clamav: { effectivePolicyId: policy, detectionNames: names },
      structuralFindings: { schemaVersion: 2 }
    }
  };
}

function fixture(result = nativeResult()) {
  const calls = [];
  const coordinator = {
    nativeScanResultsReady: true,
    readVerifiedDownloadScanReport(id) {
      calls.push(id);
      return Promise.resolve(result);
    }
  };
  const target = root();
  return {
    calls, coordinator, target,
    display: createDisplay(target, coordinator)
  };
}

const unavailable = {
  status: "unavailable", incompleteScan: false, authorizesOpen: false
};
const displayed = {
  status: "displayed", incompleteScan: true, authorizesOpen: false
};

test("displays a correlated incomplete native scan as an accessible blocking warning", async () => {
  const f = fixture();
  assert.equal(f.target.hidden, true);
  const result = await f.display.show("scan_7");
  assert.deepEqual(result, displayed);
  assert.equal(Object.isFrozen(result), true);
  assert.deepEqual(f.calls, ["scan_7"]);
  assert.equal(f.target.hidden, false);
  assert.equal(f.target.attributes.get("role"), "alert");
  assert.deepEqual(f.target.children.map(n => n.tagName), ["strong", "p"]);
  assert.match(words(f.target), /Scan incomplete — opening stopped/);
  assert.match(words(f.target), /cannot be opened until the scan completes successfully/);
  assert.equal(f.target.innerHTML, undefined);
});

test("incomplete scan remains blocked even if native evidence has signature names", async () => {
  const f = fixture(nativeResult({ names: ["Win.Test.EICAR"] }));
  assert.deepEqual(await f.display.show("scan_7"), displayed);
  assert.doesNotMatch(words(f.target), /malware detected|Win.Test.EICAR|clean/i);
  assert.equal(f.target.attributes.get("role"), "alert");
});

test("does not confuse clean, malware, scanner failure, timeout or cancelled outcomes", async () => {
  for (const status of [
    "clean", "malwareDetected", "scanFailed", "scanTimedOut", "cancelled",
    "suspiciousStructure", "encrypted", "fileChanged", "fileTooLarge",
    "unavailable", "incomplete", "incompleteScan "
  ]) {
    const f = fixture(nativeResult({ status }));
    assert.deepEqual(await f.display.show("scan_7"), unavailable, status);
    assert.equal(f.target.hidden, true);
    assert.deepEqual(f.target.children, []);
    assert.equal(f.target.attributes.has("role"), false);
  }
});

test("rejects mismatched IDs, nonblocking claims, unknown policy or schema", async () => {
  for (const response of [
    nativeResult({ id: "scan_8" }), nativeResult({ open: true }),
    nativeResult({ block: false }), nativeResult({ policy: "maximum" }),
    nativeResult({ schema: 2 }), null,
    { scanRequestId: "scan_7", report: null },
    { scanRequestId: "scan_7", report: { scan: { status: "incompleteScan" } } },
    { ...nativeResult(), authorizesOpen: false }
  ]) {
    const f = fixture(response);
    assert.deepEqual(await f.display.show("scan_7"), unavailable);
    assert.equal(f.target.hidden, true);
  }
});

test("rejects extra fields, missing evidence and untrusted structural records", async () => {
  const extra = nativeResult();
  extra.report.scan.filePath = "/private/report.pdf";
  const missing = nativeResult();
  delete missing.report.structuralFindings;
  const wrong = nativeResult();
  wrong.report.structuralFindings = ["/private"];
  for (const value of [extra, missing, wrong]) {
    const f = fixture(value);
    assert.deepEqual(await f.display.show("scan_7"), unavailable);
  }
});

test("rejects malformed signature metadata instead of surfacing raw scanner output", async () => {
  const bad = [
    ["<script>alert(1)</script>"], ["/private/report.pdf"],
    ["Win.Test.EICAR FOUND"], ["bad\nname"], ["bad:name"],
    ["Win.Test.X", "Win.Test.X"], ["x".repeat(256)],
    Array.from({ length: 257 }, (_, i) => "Win.Test." + i)
  ];
  for (const names of bad) {
    const f = fixture(nativeResult({ names }));
    assert.deepEqual(await f.display.show("scan_7"), unavailable);
    assert.equal(f.target.hidden, true);
  }
});

test("rejects accessor properties and hostile native Proxy objects", async () => {
  const hostile = new Proxy({}, { ownKeys() { throw Error("/private/secret"); } });
  const getter = nativeResult();
  Object.defineProperty(getter.report.scan, "status", {
    get() { throw Error("/private/secret"); }
  });
  const array = ["Win.Test.X"];
  Object.defineProperty(array, "0", {
    get() { throw Error("/private/secret"); }
  });
  for (const response of [
    hostile, { scanRequestId: "scan_7", report: hostile },
    getter, nativeResult({ names: array }),
    Object.assign(Object.create({ scanRequestId: "scan_7" }), {
      report: nativeResult().report
    }),
    { ...nativeResult(), [Symbol("private")]: true }
  ]) {
    const f = fixture(response);
    assert.deepEqual(await f.display.show("scan_7"), unavailable);
    assert.equal(f.target.hidden, true);
  }
});

test("requires the native result capability and a bounded scan request ID", async () => {
  for (const coordinator of [
    null, {}, { nativeScanResultsReady: true },
    { nativeScanResultsReady: false,
      readVerifiedDownloadScanReport() { throw Error("called"); } },
    { nativeScanResultsReady: true,
      get readVerifiedDownloadScanReport() { throw Error("private"); } }
  ]) {
    const target = root();
    const display = createDisplay(target, coordinator);
    assert.deepEqual(await display.show("scan_7"), unavailable);
    assert.equal(target.hidden, true);
  }
  const f = fixture();
  for (const id of [
    "", "scan/7", "../secret", "scan:7", "scan 7",
    "x".repeat(81), null, 7, undefined, {}
  ]) assert.deepEqual(await f.display.show(id), unavailable);
  assert.deepEqual(f.calls, []);
});

test("synchronous and asynchronous native failures leave a hidden fixed result", async () => {
  const f = fixture();
  f.coordinator.readVerifiedDownloadScanReport = () => {
    throw Error("/private/secret.pdf");
  };
  assert.deepEqual(await f.display.show("scan_7"), unavailable);
  f.coordinator.readVerifiedDownloadScanReport = () =>
    Promise.reject(Error("C:\\private\\secret.pdf"));
  assert.deepEqual(await f.display.show("scan_7"), unavailable);
  f.coordinator.readVerifiedDownloadScanReport = () => nativeResult();
  assert.deepEqual(await f.display.show("scan_7"), unavailable);
  assert.equal(f.target.hidden, true);
  assert.doesNotMatch(words(f.target), /private/);
});

test("revoked coordinator readiness discards an in-flight report", async () => {
  const f = fixture();
  let deliver;
  f.coordinator.readVerifiedDownloadScanReport = () =>
    new Promise((resolve) => { deliver = resolve; });
  const pending = f.display.show("scan_7");
  f.coordinator.nativeScanResultsReady = false;
  deliver(nativeResult());
  assert.deepEqual(await pending, unavailable);
  assert.equal(f.target.hidden, true);
});

test("clear and dispose invalidate stale asynchronous results", async () => {
  const f = fixture();
  let deliver;
  f.coordinator.readVerifiedDownloadScanReport = () =>
    new Promise((resolve) => { deliver = resolve; });
  const pending = f.display.show("scan_7");
  f.display.clear();
  deliver(nativeResult());
  assert.deepEqual(await pending, unavailable);
  assert.equal(f.target.hidden, true);

  const next = f.display.show("scan_7");
  f.display.dispose();
  deliver(nativeResult());
  assert.deepEqual(await next, unavailable);
  assert.deepEqual(await f.display.show("scan_7"), unavailable);
  assert.equal(f.target.hidden, true);
});

test("a newer non-incomplete result clears an earlier warning", async () => {
  const f = fixture();
  assert.deepEqual(await f.display.show("scan_7"), displayed);
  f.coordinator.readVerifiedDownloadScanReport = async () =>
    nativeResult({ status: "scanFailed" });
  assert.deepEqual(await f.display.show("scan_7"), unavailable);
  assert.deepEqual(f.target.children, []);
  assert.equal(f.target.attributes.has("role"), false);
  assert.equal(f.target.hidden, true);
});

test("import remains inert and presentation never requests native or scanner access", async () => {
  assert.throws(() => createDisplay({}, {}), TypeError);
  const code = await readFile(
    new URL("../src/download-incomplete-display.js", import.meta.url), "utf8");
  const background = await readFile(
    new URL("../src/background.js", import.meta.url), "utf8");
  assert.equal(background.trimEnd().endsWith("void 0;"), true);
  for (const forbidden of [
    "innerHTML", "document.write", "sendNativeMessage(", "connectNative(",
    "scan_and_open", "clamscan", "downloads.open(", "permissions.request(",
    "chrome.", "browser.", "storage.local", "fetch(", "node:fs"
  ]) assert.equal(code.includes(forbidden), false, forbidden);
});
