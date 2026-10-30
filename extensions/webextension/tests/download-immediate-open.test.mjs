import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";
import { subscribeToDownloadCompletions } from "../src/download-completion.js";
import { createManagedScanBeforeOpenGate } from "../src/download-managed-scan-before-open.js";

// A deterministic download-completion -> immediate managed-open race harness.
// The installed extension has no authenticated native scan coordinator yet:
// these are contract regressions, NOT live-browser opening acceptance tests.
const managedRequestId = "managed_21";

function eventSource() {
  const listeners = new Set();
  return {
    addListener(listener) { listeners.add(listener); },
    removeListener(listener) { listeners.delete(listener); },
    emit(value) { for (const listener of [...listeners]) listener(value); },
    get size() { return listeners.size; }
  };
}

function deferred() {
  let resolve;
  const promise = new Promise(done => { resolve = done; });
  return { promise, resolve };
}

function cleanScan(id = managedRequestId) {
  return {
    schemaVersion: 1, managedRequestId: id, status: "complete",
    scanCompleted: true, scanVerified: true, authorizesOpen: false,
    result: { status: "clean" }
  };
}

function state(status) {
  return { status, scanVerified: false, authorizesOpen: false, opened: false };
}

function fixture() {
  const downloads = {
    onCreated: eventSource(), onChanged: eventSource(), onErased: eventSource(),
    open() { throw Error("Uncontrolled browser opening is not part of this test"); }
  };
  const notices = [], reads = [], opens = [];
  const coordinator = {
    nativeManagedWorkflowReady: true,
    nativeScanResultsReady: true,
    nativeVerifiedOpeningReady: true,
    readVerifiedManagedScanResult(id) {
      reads.push(id);
      return Promise.resolve(cleanScan(id));
    },
    requestVerifiedManagedOpen(request) {
      opens.push(request);
      return Promise.resolve({
        accepted: true, managedRequestId: request.managedRequestId
      });
    }
  };
  const gate = createManagedScanBeforeOpenGate(coordinator);
  const stop = subscribeToDownloadCompletions(downloads, notice => notices.push(notice));
  return { downloads, notices, reads, opens, coordinator, gate, stop };
}

function finishDownload(f, extra = {}) {
  f.downloads.onChanged.emit({
    id: 21, state: { previous: "in_progress", current: "complete" },
    ...extra
  });
  assert.deepEqual(f.notices, [{ kind: "completed", id: 21 }]);
  assert.equal(Object.isFrozen(f.notices[0]), true);
}

function cleanup(f) {
  f.stop();
  f.gate.dispose();
  assert.deepEqual([
    f.downloads.onCreated.size,
    f.downloads.onChanged.size,
    f.downloads.onErased.size
  ], [0, 0, 0]);
}

test("immediate opening after download waits for a complete clean native scan", async () => {
  const f = fixture();
  const pendingScan = deferred();
  f.coordinator.readVerifiedManagedScanResult = id => {
    f.reads.push(id);
    return pendingScan.promise;
  };

  finishDownload(f);
  // The user requests managed opening in the same turn as download completion.
  const opening = f.gate.requestOpenIfScanned(managedRequestId);
  assert.deepEqual(f.reads, [managedRequestId]);
  assert.deepEqual(f.opens, [], "native opening must not race ahead of scanning");
  await Promise.resolve();
  assert.deepEqual(f.opens, [], "microtasks cannot authorize an unfinished scan");

  pendingScan.resolve(cleanScan());
  assert.deepEqual(await opening, state("request-submitted"));
  assert.deepEqual(f.opens, [{ managedRequestId }]);
  assert.deepEqual(Object.keys(f.opens[0]), ["managedRequestId"]);
  assert.equal(Object.isFrozen(f.opens[0]), true);
  cleanup(f);
});

test("opening immediately on completion with pending scan evidence fails closed", async () => {
  const f = fixture();
  f.coordinator.readVerifiedManagedScanResult = id => {
    f.reads.push(id);
    return Promise.resolve({
      ...cleanScan(id), status: "pending", scanCompleted: false,
      scanVerified: false
    });
  };
  finishDownload(f);
  assert.deepEqual(await f.gate.requestOpenIfScanned(managedRequestId),
    state("scan-not-verified"));
  assert.deepEqual(f.opens, []);
  assert.deepEqual(await f.gate.requestOpenIfScanned(managedRequestId),
    state("unavailable"), "an uncertain attempt cannot be retried blindly");
  assert.deepEqual(f.reads, [managedRequestId]);
  cleanup(f);
});

test("duplicate immediate opening attempts cannot overtake the first scan", async () => {
  const f = fixture();
  const pendingScan = deferred();
  f.coordinator.readVerifiedManagedScanResult = id => {
    f.reads.push(id);
    return pendingScan.promise;
  };
  finishDownload(f);
  const first = f.gate.requestOpenIfScanned(managedRequestId);
  const second = f.gate.requestOpenIfScanned(managedRequestId);
  f.downloads.onChanged.emit({ id: 21, state: { current: "complete" } });
  assert.equal(f.notices.length, 1, "browser completion is emitted once");
  assert.deepEqual(await second, state("unavailable"));
  assert.deepEqual(f.reads, [managedRequestId]);
  assert.deepEqual(f.opens, []);
  pendingScan.resolve(cleanScan());
  assert.deepEqual(await first, state("request-submitted"));
  assert.equal(f.opens.length, 1);
  assert.deepEqual(await f.gate.requestOpenIfScanned(managedRequestId),
    state("unavailable"));
  cleanup(f);
});

test("incomplete, malicious, failed, cancelled and changed-file scans cannot open", async () => {
  const invalid = [
    { status: "pending", scanCompleted: false },
    { status: "complete", result: { status: "malwareDetected" } },
    { status: "complete", result: { status: "scanFailed" } },
    { status: "complete", result: { status: "cancelled" } },
    { status: "complete", result: { status: "fileChanged" } },
    { status: "complete", scanVerified: false },
    { status: "complete", result: { status: "incompleteScan" } }
  ];
  for (const change of invalid) {
    const f = fixture();
    f.coordinator.readVerifiedManagedScanResult = () =>
      Promise.resolve({ ...cleanScan(), ...change });
    finishDownload(f);
    assert.deepEqual(await f.gate.requestOpenIfScanned(managedRequestId),
      state("scan-not-verified"), JSON.stringify(change));
    assert.deepEqual(f.opens, [], JSON.stringify(change));
    cleanup(f);
  }
});

test("browser safe labels and private metadata cannot create scan authorization", async () => {
  const f = fixture();
  f.coordinator.readVerifiedManagedScanResult = () => Promise.resolve({
    kind: "completed", id: 21, danger: "safe",
    scanVerified: true, result: { status: "clean" }
  });
  finishDownload(f, {
    danger: { current: "safe" },
    url: { current: "https://private.example/document.pdf" },
    filename: { current: "/private/document.pdf" },
    scanVerified: true, authorizesOpen: true
  });
  assert.deepEqual(f.notices, [{ kind: "completed", id: 21 }]);
  assert.deepEqual(await f.gate.requestOpenIfScanned(managedRequestId),
    state("scan-not-verified"));
  assert.deepEqual(f.opens, []);
  assert.doesNotMatch(JSON.stringify(f.notices), /private|danger|scanVerified/);
  cleanup(f);
});

test("native readiness revoked while immediate scan is running prevents opening", async () => {
  const f = fixture();
  const pendingScan = deferred();
  f.coordinator.readVerifiedManagedScanResult = () => pendingScan.promise;
  finishDownload(f);
  const opening = f.gate.requestOpenIfScanned(managedRequestId);
  f.coordinator.nativeVerifiedOpeningReady = false;
  pendingScan.resolve(cleanScan());
  assert.deepEqual(await opening, state("scan-not-verified"));
  assert.deepEqual(f.opens, []);
  cleanup(f);
});

test("a discarded native session cannot open on its delayed clean result", async () => {
  const f = fixture();
  const pendingScan = deferred();
  f.coordinator.readVerifiedManagedScanResult = () => pendingScan.promise;
  finishDownload(f);
  const opening = f.gate.requestOpenIfScanned(managedRequestId);
  f.gate.dispose();
  pendingScan.resolve(cleanScan());
  assert.deepEqual(await opening, state("scan-not-verified"));
  assert.deepEqual(f.opens, []);
  cleanup(f);
});

test("even after a clean scan, native acceptance is not proof the PDF opened", async () => {
  const f = fixture();
  finishDownload(f);
  const response = await f.gate.requestOpenIfScanned(managedRequestId);
  assert.deepEqual(response, state("request-submitted"));
  assert.equal(Object.isFrozen(response), true);
  assert.equal(response.opened, false);
  assert.equal(response.authorizesOpen, false);
  assert.equal(response.scanVerified, false);
  assert.deepEqual(f.opens, [{ managedRequestId }]);
  cleanup(f);
});

test("download interruption and unsubscribed listeners do not trigger opening", async () => {
  const f = fixture();
  f.downloads.onChanged.emit({ id: 21, state: { current: "interrupted" } });
  f.downloads.onChanged.emit({ id: 21, state: { current: "in_progress" } });
  assert.deepEqual(f.notices, []);
  assert.deepEqual(f.reads, []);
  assert.deepEqual(f.opens, []);
  f.stop();
  f.downloads.onChanged.emit({ id: 21, state: { current: "complete" } });
  assert.deepEqual(f.notices, []);
  cleanup(f);
});

test("race regression is passive and leaves browser and scanner privileges unchanged", async () => {
  const [background, manifestText] = await Promise.all([
    readFile(new URL("../src/background.js", import.meta.url), "utf8"),
    readFile(new URL("../manifest.json", import.meta.url), "utf8")
  ]);
  const manifest = JSON.parse(manifestText);
  assert.equal(background.trimEnd().endsWith("void 0;"), true);
  assert.deepEqual(manifest.permissions, []);
  assert.deepEqual(manifest.optional_permissions, ["downloads"]);
  assert.deepEqual(manifest.host_permissions, []);
});
