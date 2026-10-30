import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";
import { createManagedScanBeforeOpenGate } from "../src/download-managed-scan-before-open.js";

const scanId = "managed_7";
const scan = (id = scanId) => ({
  schemaVersion: 1, managedRequestId: id, status: "complete",
  scanCompleted: true, scanVerified: true, authorizesOpen: false,
  result: { status: "clean" }
});
const status = name => ({
  status: name, scanVerified: false, authorizesOpen: false, opened: false
});
const tick = () => new Promise(resolve => setImmediate(resolve));

function fixture() {
  const reads = [], opens = [];
  const coordinator = {
    nativeManagedWorkflowReady: true, nativeScanResultsReady: true,
    nativeVerifiedOpeningReady: true,
    readVerifiedManagedScanResult(id) {
      reads.push(id);
      return Promise.resolve(scan(id));
    },
    requestVerifiedManagedOpen(request) {
      opens.push(request);
      return Promise.resolve({ accepted: true, managedRequestId: request.managedRequestId });
    }
  };
  const gate = createManagedScanBeforeOpenGate(coordinator);
  return { coordinator, gate, reads, opens };
}

test("only a completed verified clean scan allows one trusted native opening request", async () => {
  const f = fixture();
  assert.deepEqual(await f.gate.requestOpenIfScanned(scanId), status("request-submitted"));
  assert.deepEqual(f.reads, [scanId]);
  assert.deepEqual(f.opens, [{ managedRequestId: scanId }]);
  assert.deepEqual(Object.keys(f.opens[0]), ["managedRequestId"]);
  assert.equal(Object.isFrozen(f.opens[0]), true);
  assert.equal(Object.isFrozen(f.gate), true);
  assert.equal(Object.isFrozen(await f.gate.requestOpenIfScanned("other")), true);
  assert.deepEqual(f.opens[1], { managedRequestId: "other" });
  f.gate.dispose();
});

test("incomplete, pending, interrupted and failed scans never invoke native opening", async () => {
  for (const altered of [
    { status: "pending" }, { status: "unavailable" },
    { status: "failed" }, { status: "interrupted" },
    { scanCompleted: false }, { scanCompleted: "true" },
    { scanVerified: false }, { scanVerified: "true" },
    { authorizesOpen: true }, { schemaVersion: 2 },
    { result: { status: "incompleteScan" } },
    { result: { status: "malwareDetected" } },
    { result: { status: "scanFailed" } },
    { result: { status: "scanTimedOut" } },
    { result: { status: "fileChanged" } },
    { result: { status: "cancelled" } },
    { result: { status: "suspiciousStructure" } },
    { result: { status: "clean", extra: true } },
    { result: null }
  ]) {
    const f = fixture();
    f.coordinator.readVerifiedManagedScanResult = id =>
      Promise.resolve({ ...scan(id), ...altered });
    assert.deepEqual(await f.gate.requestOpenIfScanned(scanId),
      status("scan-not-verified"), JSON.stringify(altered));
    assert.deepEqual(f.opens, []);
    f.gate.dispose();
  }
});

test("correlation must match the same managed request ID", async () => {
  const f = fixture();
  f.coordinator.readVerifiedManagedScanResult = () => Promise.resolve(scan("different"));
  assert.deepEqual(await f.gate.requestOpenIfScanned(scanId), status("scan-not-verified"));
  assert.deepEqual(f.opens, []);
  f.gate.dispose();
});

test("browser metadata and submission acknowledgements cannot be a native clean report", async () => {
  const f = fixture();
  for (const [i, value] of [
    { kind: "completed", id: 7, danger: "safe" },
    { status: "request-submitted", scanVerified: true },
    { accepted: true, managedRequestId: scanId, status: "clean" },
    { scanCompleted: true, result: { status: "clean" } },
    null, "clean", false
  ].entries()) {
    f.coordinator.readVerifiedManagedScanResult = () => Promise.resolve(value);
    assert.deepEqual(await f.gate.requestOpenIfScanned("job_" + i),
      status("scan-not-verified"));
  }
  assert.deepEqual(f.opens, []);
  f.gate.dispose();
});

test("scan report rejects inherited, accessor, symbol and extra fields", async () => {
  const f = fixture();
  const cases = [
    (id) => Object.assign(Object.create({ scanVerified: true }), {
      schemaVersion: 1, managedRequestId: id, status: "complete",
      scanCompleted: true, authorizesOpen: false, result: { status: "clean" }
    }),
    (id) => ({ ...scan(id), nativePath: "/private/a.pdf" }),
    (id) => {
      const value = scan(id);
      value[Symbol("hidden")] = true;
      return value;
    },
    (id) => {
      const value = scan(id);
      Object.defineProperty(value, "scanVerified", {
        get() { throw Error("/private/secret.pdf"); }
      });
      return value;
    },
    (id) => {
      const value = scan(id);
      Object.defineProperty(value.result, "status", {
        get() { throw Error("secret"); }
      });
      return value;
    },
    (id) => ({ ...scan(id), result: Object.assign(Object.create(null), { status: "clean", extra: true }) })
  ];
  for (const [i, make] of cases.entries()) {
    f.coordinator.readVerifiedManagedScanResult = id => Promise.resolve(make(id));
    assert.deepEqual(await f.gate.requestOpenIfScanned("job_" + i),
      status("scan-not-verified"));
  }
  assert.deepEqual(f.opens, []);
  f.gate.dispose();
});

test("invalid IDs or absent trusted coordinator never call a scan reader", async () => {
  const f = fixture();
  for (const id of [
    null, undefined, 7, "", "/", "foo/bar", "abc\nx", "abc x",
    "a".repeat(81), {}, [], "日本語"
  ]) assert.deepEqual(await f.gate.requestOpenIfScanned(id), status("unavailable"));
  assert.deepEqual(f.reads, []);
  assert.deepEqual(f.opens, []);
  f.gate.dispose();
  const absent = createManagedScanBeforeOpenGate(undefined);
  assert.deepEqual(await absent.requestOpenIfScanned(scanId), status("unavailable"));
  absent.dispose();
});

test("readiness flags are not substitutes for native scan evidence", async () => {
  for (const key of [
    "nativeManagedWorkflowReady", "nativeScanResultsReady",
    "nativeVerifiedOpeningReady", "readVerifiedManagedScanResult",
    "requestVerifiedManagedOpen"
  ]) {
    const f = fixture();
    f.coordinator[key] = undefined;
    assert.deepEqual(await f.gate.requestOpenIfScanned(scanId), status("unavailable"));
    assert.deepEqual(f.reads, []);
    assert.deepEqual(f.opens, []);
    f.gate.dispose();
  }
});

test("revoked native readiness during asynchronous scan check prevents all opening", async () => {
  const f = fixture();
  let finish;
  f.coordinator.readVerifiedManagedScanResult = () =>
    new Promise(resolve => { finish = resolve; });
  const pending = f.gate.requestOpenIfScanned(scanId);
  f.coordinator.nativeScanResultsReady = false;
  finish(scan());
  assert.deepEqual(await pending, status("scan-not-verified"));
  assert.deepEqual(f.opens, []);
  f.gate.dispose();
});

test("synchronous reservation prevents concurrent and reentrant opening commands", async () => {
  const f = fixture();
  let release;
  let calls = 0;
  f.coordinator.readVerifiedManagedScanResult = () => {
    calls++;
    return new Promise(resolve => { release = resolve; });
  };
  const first = f.gate.requestOpenIfScanned(scanId);
  assert.deepEqual(await f.gate.requestOpenIfScanned(scanId), status("unavailable"));
  assert.equal(calls, 1);
  release(scan());
  assert.deepEqual(await first, status("request-submitted"));
  assert.equal(f.opens.length, 1);
  assert.deepEqual(await f.gate.requestOpenIfScanned(scanId), status("unavailable"));
  f.gate.dispose();
});

test("rejected or ambiguous scan proof cannot be retried with the same request ID", async () => {
  const f = fixture();
  let reads = 0;
  f.coordinator.readVerifiedManagedScanResult = () => {
    reads++;
    return Promise.resolve({ ...scan(), scanCompleted: false });
  };
  assert.deepEqual(await f.gate.requestOpenIfScanned(scanId), status("scan-not-verified"));
  f.coordinator.readVerifiedManagedScanResult = () => {
    reads++;
    return Promise.resolve(scan());
  };
  assert.deepEqual(await f.gate.requestOpenIfScanned(scanId), status("unavailable"));
  assert.equal(reads, 1);
  assert.deepEqual(f.opens, []);
  f.gate.dispose();
});

test("an uncorrelated, rejected or hostile native opening acknowledgement never claims opening", async () => {
  for (const reply of [
    { accepted: false, managedRequestId: scanId },
    { accepted: true, managedRequestId: "different" },
    { accepted: "true", managedRequestId: scanId },
    { accepted: true, managedRequestId: scanId, opened: true },
    null, undefined, "accepted"
  ]) {
    const f = fixture();
    f.coordinator.requestVerifiedManagedOpen = request => {
      f.opens.push(request);
      return Promise.resolve(reply);
    };
    assert.deepEqual(await f.gate.requestOpenIfScanned(scanId), status("unavailable"));
    assert.equal(f.opens.length, 1);
    assert.deepEqual(await f.gate.requestOpenIfScanned(scanId), status("unavailable"));
    f.gate.dispose();
  }
});

test("scanner errors and opening errors fail closed without exposing private details", async () => {
  for (const failedMethod of ["readVerifiedManagedScanResult", "requestVerifiedManagedOpen"]) {
    const f = fixture();
    f.coordinator[failedMethod] = () => Promise.reject(Error("/private/secret.pdf"));
    const outcome = await f.gate.requestOpenIfScanned(scanId);
    assert.equal(outcome.status, "unavailable");
    assert.equal(JSON.stringify(outcome).includes("private"), false);
    assert.equal(outcome.authorizesOpen, false);
    assert.equal(outcome.opened, false);
    if (failedMethod === "readVerifiedManagedScanResult") assert.deepEqual(f.opens, []);
    f.gate.dispose();
  }
});

test("disposal before scan resolves cannot authorize or dispatch a native open", async () => {
  const f = fixture();
  let finish;
  f.coordinator.readVerifiedManagedScanResult = () =>
    new Promise(resolve => { finish = resolve; });
  const pending = f.gate.requestOpenIfScanned(scanId);
  f.gate.dispose();
  finish(scan());
  assert.deepEqual(await pending, status("scan-not-verified"));
  assert.deepEqual(f.opens, []);
  assert.deepEqual(await f.gate.requestOpenIfScanned("other"), status("unavailable"));
  f.gate.dispose();
});

test("disposal during an already dispatched command never asserts a PDF was opened", async () => {
  const f = fixture();
  let finish;
  f.coordinator.requestVerifiedManagedOpen = request => {
    f.opens.push(request);
    return new Promise(resolve => { finish = resolve; });
  };
  const pending = f.gate.requestOpenIfScanned(scanId);
  await tick();
  assert.equal(f.opens.length, 1);
  f.gate.dispose();
  finish({ accepted: true, managedRequestId: scanId });
  assert.deepEqual(await pending, status("unavailable"));
});

test("the module is inert and does not alter the shipped browser, scanner or settings", async () => {
  const source = await readFile(new URL("../src/download-managed-scan-before-open.js", import.meta.url), "utf8");
  const worker = await readFile(new URL("../src/background.js", import.meta.url), "utf8");
  const manifest = JSON.parse(await readFile(new URL("../manifest.json", import.meta.url), "utf8"));
  assert.equal(worker.trimEnd().endsWith("void 0;"), true);
  assert.deepEqual(manifest.permissions, []);
  assert.deepEqual(manifest.optional_permissions, ["downloads"]);
  assert.deepEqual(manifest.host_permissions, []);
  for (const forbidden of [
    "downloads.open(", "window.open(", "scan-and-open.py", "connectNative(",
    "sendNativeMessage(", "fetch(", "node:fs", "storage.local", "permissions.request("
  ]) assert.equal(source.includes(forbidden), false, forbidden);
});
