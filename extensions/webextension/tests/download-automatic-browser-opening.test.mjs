import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";
import { subscribeToDownloadEvents } from "../src/download-monitoring.js";
import { createManagedScanBeforeOpenGate } from "../src/download-managed-scan-before-open.js";

const requestId = "automatic_test_1";
const cleanScan = (id = requestId) => ({
  schemaVersion: 1, managedRequestId: id, status: "complete",
  scanCompleted: true, scanVerified: true, authorizesOpen: false,
  result: { status: "clean" }
});

function eventSource() {
  const listeners = new Set();
  return {
    addListener(listener) { listeners.add(listener); },
    removeListener(listener) { listeners.delete(listener); },
    emit(payload) { for (const listener of [...listeners]) listener(payload); },
    get size() { return listeners.size; }
  };
}

function simulatedBrowser() {
  const downloads = {
    onCreated: eventSource(),
    onChanged: eventSource(),
    onErased: eventSource()
  };
  // Deliberately outside the extension API: a browser's own auto-open setting
  // is not a cancellable download event or a PDF Magic native open command.
  const automaticOpens = [];
  return {
    downloads, automaticOpens,
    autoOpen(id) { automaticOpens.push(id); }
  };
}

function managedSession(readScan = id => Promise.resolve(cleanScan(id))) {
  const nativeOpens = [];
  const coordinator = {
    nativeManagedWorkflowReady: true,
    nativeScanResultsReady: true,
    nativeVerifiedOpeningReady: true,
    readVerifiedManagedScanResult: readScan,
    requestVerifiedManagedOpen(request) {
      nativeOpens.push(request);
      return Promise.resolve({ accepted: true, managedRequestId: request.managedRequestId });
    }
  };
  return { coordinator, gate: createManagedScanBeforeOpenGate(coordinator), nativeOpens };
}

function assertNoOpeningAuthority(outcome) {
  assert.equal(outcome.scanVerified, false);
  assert.equal(outcome.authorizesOpen, false);
  assert.equal(outcome.opened, false);
}

test("browser auto-open remains independent of a noncancellable completion observation", () => {
  const browser = simulatedBrowser();
  const observed = [];
  const stop = subscribeToDownloadEvents(browser.downloads, event => {
    observed.push(event);
    return false; // Download events provide no veto or wait-for-scan contract.
  });
  browser.downloads.onChanged.emit({ id: 7, state: { current: "complete" },
    danger: { current: "safe" } });
  browser.autoOpen(7);
  assert.deepEqual(observed, [{ kind: "changed", id: 7,
    state: "complete", danger: "safe" }]);
  assert.deepEqual(browser.automaticOpens, [7]);
  stop();
});

test("auto-open before observer registration cannot be retroactively intercepted", () => {
  const browser = simulatedBrowser();
  browser.autoOpen(8);
  const observed = [];
  const stop = subscribeToDownloadEvents(browser.downloads, event => observed.push(event));
  assert.deepEqual(observed, []);
  assert.deepEqual(browser.automaticOpens, [8]);
  stop();
});

test("browser-complete and safe labels cannot substitute for verified native scan evidence", async () => {
  const browser = simulatedBrowser();
  let latestEvent;
  const stop = subscribeToDownloadEvents(browser.downloads, event => { latestEvent = event; });
  browser.downloads.onChanged.emit({ id: 9, state: { current: "complete" },
    danger: { current: "safe" } });
  const session = managedSession(() => Promise.resolve(latestEvent));
  const outcome = await session.gate.requestOpenIfScanned(requestId);
  assert.equal(outcome.status, "scan-not-verified");
  assertNoOpeningAuthority(outcome);
  assert.deepEqual(session.nativeOpens, []);
  browser.autoOpen(9);
  assert.deepEqual(browser.automaticOpens, [9]);
  stop();
  session.gate.dispose();
});

test("browser automatic opening can precede completion of a pending native scan", async () => {
  const browser = simulatedBrowser();
  let finishScan;
  const session = managedSession(() => new Promise(resolve => { finishScan = resolve; }));
  const pending = session.gate.requestOpenIfScanned(requestId);
  browser.downloads.onChanged.emit({ id: 10, state: { current: "complete" } });
  browser.autoOpen(10);
  assert.deepEqual(browser.automaticOpens, [10]);
  assert.deepEqual(session.nativeOpens, []);
  finishScan({ ...cleanScan(), status: "interrupted" });
  const outcome = await pending;
  assert.equal(outcome.status, "scan-not-verified");
  assertNoOpeningAuthority(outcome);
  assert.deepEqual(session.nativeOpens, []);
  session.gate.dispose();
});

test("failed or mismatched native scans cannot cause an additional managed opening", async () => {
  for (const invalid of [
    { ...cleanScan(), result: { status: "malwareDetected" } },
    { ...cleanScan(), scanCompleted: false },
    { ...cleanScan(), managedRequestId: "other" },
    { ...cleanScan(), scanVerified: false },
    null
  ]) {
    const session = managedSession(() => Promise.resolve(invalid));
    const outcome = await session.gate.requestOpenIfScanned(requestId);
    assert.equal(outcome.status, "scan-not-verified");
    assertNoOpeningAuthority(outcome);
    assert.deepEqual(session.nativeOpens, []);
    session.gate.dispose();
  }
});

test("only an independently verified native result can queue one managed open", async () => {
  const browser = simulatedBrowser();
  const session = managedSession();
  browser.autoOpen(11); // Uncontrolled browser action is a distinct path.
  const first = await session.gate.requestOpenIfScanned(requestId);
  assert.equal(first.status, "request-submitted");
  assertNoOpeningAuthority(first); // Even an accepted command does not prove opening.
  assert.deepEqual(session.nativeOpens, [{ managedRequestId: requestId }]);
  assert.equal(Object.isFrozen(session.nativeOpens[0]), true);
  const repeat = await session.gate.requestOpenIfScanned(requestId);
  assert.equal(repeat.status, "unavailable");
  assertNoOpeningAuthority(repeat);
  assert.equal(session.nativeOpens.length, 1);
  assert.deepEqual(browser.automaticOpens, [11]);
  session.gate.dispose();
});

test("stopping download observation cannot disable a browser-owned auto-open preference", () => {
  const browser = simulatedBrowser();
  const seen = [];
  const stop = subscribeToDownloadEvents(browser.downloads, event => seen.push(event));
  stop();
  browser.downloads.onChanged.emit({ id: 12, state: { current: "complete" } });
  browser.autoOpen(12);
  assert.deepEqual(seen, []);
  assert.deepEqual(browser.automaticOpens, [12]);
  assert.equal(browser.downloads.onChanged.size, 0);
});

test("shipped extension cannot claim to intercept or silently enable automatic opening", async () => {
  const [background, manifestText] = await Promise.all([
    readFile(new URL("../src/background.js", import.meta.url), "utf8"),
    readFile(new URL("../manifest.json", import.meta.url), "utf8")
  ]);
  const manifest = JSON.parse(manifestText);
  assert.equal(background.trimEnd().endsWith("void 0;"), true);
  assert.deepEqual(manifest.permissions, []);
  assert.deepEqual(manifest.host_permissions, []);
  assert.deepEqual(manifest.optional_permissions, ["downloads"]);
  assert.equal(manifest.permissions.includes("downloads.open"), false);
  assert.equal(manifest.permissions.includes("nativeMessaging"), false);
});
