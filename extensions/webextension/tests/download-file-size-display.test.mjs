import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";
import {
  createDownloadFileSizeFailureDisplay as createDisplay
} from "../src/download-file-size-display.js";

function element(tagName = "section", ownerDocument = null) {
  return {
    tagName, nodeType: 1, ownerDocument, hidden: false, children: [],
    textContent: "", attributes: new Map(),
    replaceChildren(...nodes) { this.children = nodes; this.textContent = ""; },
    setAttribute(key, value) { this.attributes.set(key, value); },
    removeAttribute(key) { this.attributes.delete(key); }
  };
}
function root() {
  const doc = { createElement(tag) { return element(tag, doc); } };
  return element("section", doc);
}
const words = node => [node.textContent, ...node.children.map(words)].filter(Boolean).join(" ");
const unavailable = { status: "unavailable", fileSizeFailure: false, authorizesOpen: false };

function nativeResult({
  id = "scan_7", status = "fileTooLarge", blocked = true,
  authorizesOpen = false, policy = "built-in", schemaVersion = 1,
  names = [], structural = { schemaVersion: 2 }
} = {}) {
  return {
    scanRequestId: id,
    report: {
      schemaVersion, authorizesOpen, requiresBlock: blocked,
      scan: { status },
      clamav: { effectivePolicyId: policy, detectionNames: names },
      structuralFindings: structural
    }
  };
}

function fixture(response = nativeResult()) {
  const calls = [];
  const coordinator = {
    nativeScanResultsReady: true,
    readVerifiedDownloadScanReport(id) {
      calls.push(id);
      return Promise.resolve(response);
    }
  };
  const target = root();
  return { coordinator, target, calls, display: createDisplay(target, coordinator) };
}

test("displays only a correlated verified native fileTooLarge outcome as an accessible blocked warning", async () => {
  const f = fixture();
  assert.equal(f.target.hidden, true);
  const result = await f.display.show("scan_7");
  assert.deepEqual(result, {
    status: "displayed", fileSizeFailure: true, authorizesOpen: false
  });
  assert.equal(Object.isFrozen(result), true);
  assert.deepEqual(f.calls, ["scan_7"]);
  assert.equal(f.target.hidden, false);
  assert.equal(f.target.attributes.get("role"), "alert");
  assert.deepEqual(f.target.children.map(x => x.tagName), ["strong", "p"]);
  assert.match(words(f.target), /File too large — scanning blocked/);
  assert.match(words(f.target), /PDF was not opened/);
  assert.equal(f.target.innerHTML, undefined);
});

test("never invents byte counts, scanner thresholds or unsupported remedies", async () => {
  const f = fixture();
  f.coordinator.readVerifiedDownloadScanReport = async () => {
    const response = nativeResult();
    response.report.diagnostics = "/private/report.pdf";
    return response;
  };
  assert.deepEqual(await f.display.show("scan_7"), unavailable);
  assert.equal(f.target.hidden, true);
  f.coordinator.readVerifiedDownloadScanReport = async () => nativeResult();
  assert.equal((await f.display.show("scan_7")).status, "displayed");
  assert.doesNotMatch(words(f.target),
    /MB|MiB|GB|GiB|bytes|maximum of|increase the limit|\/private\/|https?:|scan_7/iu);
});

test("never mislabels clean, infected, timed-out, cancelled or generic scanner failures as size failures", async () => {
  for (const status of [
    "clean", "malwareDetected", "scanFailed", "scanTimedOut", "cancelled",
    "incompleteScan", "fileChanged", "encrypted", "suspiciousStructure",
    "fileTooLarge ", "tooLarge", "", null
  ]) {
    const f = fixture(nativeResult({ status }));
    assert.deepEqual(await f.display.show("scan_7"), unavailable, String(status));
    assert.equal(f.target.hidden, true);
    assert.equal(f.target.attributes.has("role"), false);
  }
});

test("requires canonical blocked Built-in result and exact scan-request correlation", async () => {
  const responses = [
    nativeResult({ id: "other" }),
    nativeResult({ blocked: false }),
    nativeResult({ authorizesOpen: true }),
    nativeResult({ policy: "maximum" }),
    nativeResult({ schemaVersion: 2 }),
    { ...nativeResult(), accepted: true },
    { scanRequestId: "scan_7", report: { scan: { status: "fileTooLarge" } } },
    { scanRequestId: "scan_7", report: null },
    null,
    { ...nativeResult(), report: { ...nativeResult().report,
      scan: { status: "fileTooLarge", size: 123 } } },
    { ...nativeResult(), report: { ...nativeResult().report,
      clamav: { effectivePolicyId: "built-in", detectionNames: [],
        rawLog: "/private/report.pdf" } } }
  ];
  for (const response of responses) {
    const f = fixture(response);
    assert.deepEqual(await f.display.show("scan_7"), unavailable);
    assert.equal(f.target.hidden, true);
  }
});

test("cannot downgrade a malware-bearing result into a size-only warning", async () => {
  for (const names of [["Win.Test.EICAR"], ["Win.Test.EICAR", "Win.Other"],
    null, "Win.Test.EICAR", [undefined]]) {
    const f = fixture(nativeResult({ names }));
    assert.deepEqual(await f.display.show("scan_7"), unavailable);
    assert.equal(f.target.hidden, true);
  }
  const names = [];
  names.extra = "/private/file.pdf";
  const f = fixture(nativeResult({ names }));
  assert.deepEqual(await f.display.show("scan_7"), unavailable);
});

test("rejects hostile report objects and accessors without executing getters or revealing paths", async () => {
  let reads = 0;
  const accessor = nativeResult();
  Object.defineProperty(accessor.report.scan, "status", {
    get() { reads += 1; throw Error("/private/secret.pdf"); }
  });
  const proxy = new Proxy({}, { ownKeys() { throw Error("C:\\secret.pdf"); } });
  for (const response of [
    accessor, proxy, { scanRequestId: "scan_7", report: proxy },
    { ...nativeResult(), [Symbol("url")]: "https://private.invalid" },
    Object.assign(Object.create({ scanRequestId: "scan_7" }), {
      report: nativeResult().report
    }),
    { ...nativeResult(), report: { ...nativeResult().report,
      structuralFindings: null } },
    { ...nativeResult(), report: { ...nativeResult().report,
      structuralFindings: "unverified" } }
  ]) {
    const f = fixture(response);
    assert.deepEqual(await f.display.show("scan_7"), unavailable);
    assert.equal(f.target.hidden, true);
    assert.deepEqual(f.target.children, []);
  }
  assert.equal(reads, 0);
});

test("requires independently ready native results and bounded valid scan-request IDs", async () => {
  for (const coordinator of [
    null, {}, { nativeScanResultsReady: true },
    { nativeScanResultsReady: false,
      readVerifiedDownloadScanReport() { throw Error("not called"); } },
    { nativeScanResultsReady: true,
      get readVerifiedDownloadScanReport() { throw Error("/private/path"); } }
  ]) {
    const target = root();
    const display = createDisplay(target, coordinator);
    assert.deepEqual(await display.show("scan_7"), unavailable);
    assert.equal(target.hidden, true);
  }
  const f = fixture();
  for (const id of ["", "/tmp/report.pdf", "scan:7", "scan 7",
    "x".repeat(81), 7, null, {}, undefined]) {
    assert.deepEqual(await f.display.show(id), unavailable);
  }
  assert.deepEqual(f.calls, []);
});

test("native errors and non-Promise replies cannot display a size failure", async () => {
  const f = fixture();
  for (const method of [
    () => { throw Error("C:\\private\\document.pdf"); },
    () => Promise.reject(Error("/private/native-report")),
    () => nativeResult(),
    () => null
  ]) {
    f.coordinator.readVerifiedDownloadScanReport = method;
    assert.deepEqual(await f.display.show("scan_7"), unavailable);
    assert.equal(f.target.hidden, true);
    assert.deepEqual(f.target.children, []);
  }
});

test("clear invalidates late in-flight results and removes alert semantics", async () => {
  const f = fixture();
  let deliver;
  f.coordinator.readVerifiedDownloadScanReport = () =>
    new Promise(resolve => { deliver = resolve; });
  const pending = f.display.show("scan_7");
  f.display.clear();
  deliver(nativeResult());
  assert.deepEqual(await pending, unavailable);
  assert.equal(f.target.hidden, true);
  assert.equal(f.target.attributes.has("role"), false);
});

test("newer request cannot be overwritten by an earlier late response", async () => {
  const f = fixture();
  const deliveries = [];
  f.coordinator.readVerifiedDownloadScanReport = () =>
    new Promise(resolve => { deliveries.push(resolve); });
  const first = f.display.show("scan_7");
  const second = f.display.show("scan_8");
  deliveries[1](nativeResult({ id: "scan_8" }));
  assert.equal((await second).status, "displayed");
  deliveries[0](nativeResult({ id: "scan_7" }));
  assert.deepEqual(await first, unavailable);
  assert.equal(f.target.hidden, false);
  assert.match(words(f.target), /File too large/);
});

test("later clean or unverified response clears an earlier size failure", async () => {
  const f = fixture();
  assert.equal((await f.display.show("scan_7")).status, "displayed");
  f.coordinator.readVerifiedDownloadScanReport = async () =>
    nativeResult({ status: "clean", blocked: false });
  assert.deepEqual(await f.display.show("scan_7"), unavailable);
  assert.equal(f.target.hidden, true);
  assert.equal(f.target.attributes.has("role"), false);
  assert.deepEqual(f.target.children, []);
});

test("dispose prevents stale results and all further updates", async () => {
  const f = fixture();
  let deliver;
  f.coordinator.readVerifiedDownloadScanReport = () =>
    new Promise(resolve => { deliver = resolve; });
  const pending = f.display.show("scan_7");
  f.display.dispose();
  deliver(nativeResult());
  assert.deepEqual(await pending, unavailable);
  assert.deepEqual(await f.display.show("scan_7"), unavailable);
  assert.equal(f.target.hidden, true);
});

test("import remains inert and display never scans, opens or mutates user preferences", async () => {
  assert.throws(() => createDisplay({}, {}), TypeError);
  const code = await readFile(
    new URL("../src/download-file-size-display.js", import.meta.url), "utf8");
  const background = await readFile(
    new URL("../src/background.js", import.meta.url), "utf8");
  assert.equal(background.trimEnd().endsWith("void 0;"), true);
  for (const forbidden of [
    "innerHTML", "document.write", "sendNativeMessage(", "connectNative(",
    "scan_and_open", "clamscan", "downloads.open(", "permissions.request(",
    "chrome.", "browser.", "storage.local", "fetch(", "node:fs"
  ]) {
    assert.equal(code.includes(forbidden), false, forbidden);
  }
});
