import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

import { subscribeToDownloadEvents } from "../src/download-monitoring.js";
import { assessDownloadOpeningBeforeMonitoringCompletes } from "../src/download-early-open-assessment.js";
import { createManagedScanBeforeOpenGate } from "../src/download-managed-scan-before-open.js";

// The browser's Downloads/History UI is deliberately NOT downloads.open().
// A WebExtension download observer cannot intercept the browser-owned click.
// This fake tests our integration's security claims, not live browser behavior.
function eventSource() {
  const listeners = new Set();
  return {
    addListener(listener) { listeners.add(listener); },
    removeListener(listener) { listeners.delete(listener); },
    emit(value) { for (const listener of [...listeners]) listener(value); },
    get count() { return listeners.size; }
  };
}

function fixture() {
  const browserOpens = [];
  const nativeOpens = [];
  const nativeReads = [];
  const observed = [];
  const searches = [];
  const row = {
    id: 17, state: "complete", exists: true, paused: false,
    canResume: false, danger: "safe", filename: "/example/download.pdf",
    url: "https://example.invalid/download.pdf", referrer: "https://example.invalid/"
  };
  const downloads = {
    onCreated: eventSource(),
    onChanged: eventSource(),
    onErased: eventSource(),
    search(query) {
      searches.push(query);
      return Promise.resolve([{ ...row }]);
    },
    open() { throw Error("The extension must not invoke downloads.open"); },
    pause() { throw Error("The extension must not pause downloads"); },
    cancel() { throw Error("The extension must not cancel downloads"); }
  };
  const permissions = {
    onRemoved: eventSource(),
    contains() { return Promise.resolve(true); },
    request() { throw Error("The extension must not request new privileges"); }
  };
  const coordinator = {
    nativeManagedWorkflowReady: true,
    nativeScanResultsReady: true,
    nativeVerifiedOpeningReady: true,
    readVerifiedManagedScanResult(id) {
      nativeReads.push(id);
      return Promise.resolve({
        schemaVersion: 1, managedRequestId: id, status: "complete",
        scanCompleted: true, scanVerified: true, authorizesOpen: false,
        result: { status: "clean" }
      });
    },
    requestVerifiedManagedOpen(request) {
      nativeOpens.push(request);
      return Promise.resolve({ accepted: true, managedRequestId: request.managedRequestId });
    }
  };
  const history = {
    // Explicitly model the browser-owned download-history command, not an
    // extension callback or an approved PDF Magic native handoff.
    open(id = 17) {
      browserOpens.push(id);
      return Object.freeze({ openedByBrowserUi: true, downloadId: id });
    }
  };
  return {
    row, downloads, permissions, coordinator, history,
    browserOpens, nativeOpens, nativeReads, observed, searches
  };
}

function assertNoManagedOpen(f) {
  assert.deepEqual(f.nativeReads, []);
  assert.deepEqual(f.nativeOpens, []);
}

function assertNotAuthorized(value) {
  assert.equal(value.scanVerified, false);
  assert.equal(value.authorizesOpen, false);
  if (Object.hasOwn(value, "openingBlocked")) {
    assert.equal(value.openingBlocked, false);
  }
}

const pending = id => Object.freeze({ kind: "monitoring-pending", id });

test("opening a completed PDF from browser history does not trigger native scanning or managed opening", async () => {
  const f = fixture();
  assert.deepEqual(f.history.open(), { openedByBrowserUi: true, downloadId: 17 });
  assertNoManagedOpen(f);
  const assessment = await assessDownloadOpeningBeforeMonitoringCompletes(
    f.downloads, f.permissions, pending(17)
  );
  assert.equal(assessment.status, "opening-possible");
  assert.equal(assessment.browserMayOpenBeforeMonitoringCompletes, true);
  assertNotAuthorized(assessment);
  assert.deepEqual(f.searches, [{ id: 17 }]);
  assert.deepEqual(f.browserOpens, [17]);
  assertNoManagedOpen(f);
});

test("download event notifications cannot veto a browser history open", () => {
  const f = fixture();
  const stop = subscribeToDownloadEvents(f.downloads, event => {
    f.observed.push(event);
    return false; // Observer return values cannot cancel browser UI opens.
  });
  f.downloads.onChanged.emit({ id: 17, state: { current: "complete" } });
  const opened = f.history.open();
  assert.equal(opened.openedByBrowserUi, true);
  assert.deepEqual(f.observed, [{ kind: "changed", id: 17, state: "complete" }]);
  assert.deepEqual(f.browserOpens, [17]);
  assertNoManagedOpen(f);
  stop();
  assert.equal(f.downloads.onChanged.count, 0);
  assert.equal(f.downloads.onCreated.count, 0);
  assert.equal(f.downloads.onErased.count, 0);
});

test("browser history can open while the exact-ID permissioned monitoring lookup is pending", async () => {
  const f = fixture();
  let completeSearch;
  f.downloads.search = query => {
    f.searches.push(query);
    return new Promise(resolve => { completeSearch = resolve; });
  };
  const assessing = assessDownloadOpeningBeforeMonitoringCompletes(
    f.downloads, f.permissions, pending(17)
  );
  await new Promise(resolve => setImmediate(resolve));
  assert.deepEqual(f.searches, [{ id: 17 }]);
  f.history.open();
  assertNoManagedOpen(f);
  completeSearch([{ ...f.row }]);
  const assessment = await assessing;
  assert.equal(assessment.status, "opening-possible");
  assertNotAuthorized(assessment);
  assert.deepEqual(f.browserOpens, [17]);
});

test("completed, safe-labeled and dangerous-labeled history entries are never scan evidence", async () => {
  for (const danger of ["safe", "accepted", "dangerous", "uncommon", "unknown"]) {
    const f = fixture();
    f.row.danger = danger;
    f.history.open();
    const assessment = await assessDownloadOpeningBeforeMonitoringCompletes(
      f.downloads, f.permissions, pending(17)
    );
    assert.equal(assessment.status, "opening-possible", danger);
    assertNotAuthorized(assessment);
    assertNoManagedOpen(f);
    assert.doesNotMatch(JSON.stringify(assessment), /example\\.invalid|download\\.pdf/);
  }
});

test("denied downloads permission does not turn browser history opening into an enforced block", async () => {
  const f = fixture();
  f.permissions.contains = () => Promise.resolve(false);
  f.history.open();
  const assessment = await assessDownloadOpeningBeforeMonitoringCompletes(
    f.downloads, f.permissions, pending(17)
  );
  assert.equal(assessment.status, "unknown");
  assertNotAuthorized(assessment);
  assert.deepEqual(f.searches, []);
  assert.deepEqual(f.browserOpens, [17]);
  assertNoManagedOpen(f);
});

test("erased, missing or incomplete history records never manufacture a clean verdict", async () => {
  for (const update of [
    { state: "in_progress" }, { state: "interrupted" }, { exists: false },
    { paused: true }, { error: "NETWORK_FAILED" }
  ]) {
    const f = fixture();
    Object.assign(f.row, update);
    f.history.open();
    const assessment = await assessDownloadOpeningBeforeMonitoringCompletes(
      f.downloads, f.permissions, pending(17)
    );
    assertNotAuthorized(assessment);
    assertNoManagedOpen(f);
  }
  const f = fixture();
  f.downloads.search = () => Promise.resolve([]);
  f.history.open();
  const unknown = await assessDownloadOpeningBeforeMonitoringCompletes(
    f.downloads, f.permissions, pending(17)
  );
  assert.equal(unknown.status, "unknown");
  assertNotAuthorized(unknown);
});

test("browser history metadata cannot substitute for a trusted native clean scan", async () => {
  const f = fixture();
  f.coordinator.readVerifiedManagedScanResult = id => {
    f.nativeReads.push(id);
    return Promise.resolve({
      id: 17, state: "complete", danger: "safe", scanVerified: true,
      managedRequestId: id, result: { status: "clean" }
    });
  };
  const gate = createManagedScanBeforeOpenGate(f.coordinator);
  f.history.open();
  assertNoManagedOpen(f);
  const result = await gate.requestOpenIfScanned("history_17");
  assert.equal(result.status, "scan-not-verified");
  assertNotAuthorized(result);
  assert.deepEqual(f.nativeReads, ["history_17"]);
  assert.deepEqual(f.nativeOpens, []);
  gate.dispose();
});

test("only an explicit verified native workflow can submit a native open, not history clicks", async () => {
  const f = fixture();
  const gate = createManagedScanBeforeOpenGate(f.coordinator);
  f.history.open();
  f.history.open();
  assertNoManagedOpen(f);
  assert.equal((await gate.requestOpenIfScanned("managed_17")).status, "request-submitted");
  assert.deepEqual(f.nativeReads, ["managed_17"]);
  assert.deepEqual(f.nativeOpens, [{ managedRequestId: "managed_17" }]);
  assert.equal(Object.isFrozen(f.nativeOpens[0]), true);
  assert.equal((await gate.requestOpenIfScanned("managed_17")).opened, false);
  assert.deepEqual(f.browserOpens, [17, 17]);
  gate.dispose();
});

test("history opening cannot cause a native open when the native scan is incomplete", async () => {
  const f = fixture();
  f.coordinator.readVerifiedManagedScanResult = id => {
    f.nativeReads.push(id);
    return Promise.resolve({
      schemaVersion: 1, managedRequestId: id, status: "complete",
      scanCompleted: false, scanVerified: false, authorizesOpen: false,
      result: { status: "incompleteScan" }
    });
  };
  const gate = createManagedScanBeforeOpenGate(f.coordinator);
  f.history.open();
  const result = await gate.requestOpenIfScanned("history_17");
  assert.equal(result.status, "scan-not-verified");
  assertNotAuthorized(result);
  assert.deepEqual(f.nativeOpens, []);
  gate.dispose();
});

test("download-history acceptance instructions and inert extension protections stay in CI", async () => {
  const [guide, support, background, manifestText, workflow] = await Promise.all([
    readFile(new URL("../../../docs/download-history-open-testing.md", import.meta.url), "utf8"),
    readFile(new URL("../../../docs/download-opening-browser-support.md", import.meta.url), "utf8"),
    readFile(new URL("../src/background.js", import.meta.url), "utf8"),
    readFile(new URL("../manifest.json", import.meta.url), "utf8"),
    readFile(new URL("../../../.github/workflows/ci.yml", import.meta.url), "utf8")
  ]);
  for (const required of [
    "download history", "Chrome", "Firefox", "Safari", "manual",
    "pending", "browser-owned", "not intercepted", "selected application"
  ]) assert.ok(guide.toLowerCase().includes(required.toLowerCase()), required);
  assert.match(support, /Browser-owned opening/);
  assert.match(workflow, /scanner-tests:/);
  assert.match(workflow, /npm test/);
  assert.equal(background.trimEnd().endsWith("void 0;"), true);
  const manifest = JSON.parse(manifestText);
  assert.deepEqual(manifest.permissions, []);
  assert.deepEqual(manifest.host_permissions, []);
  assert.deepEqual(manifest.optional_permissions, ["downloads"]);
  assert.equal(manifest.permissions.includes("downloads.open"), false);
});

test("opener-1069 exercises live Chromium history rather than faking a history click", async () => {
  const [smoke, workflow, manifest, worker] = await Promise.all([
    readFile(new URL("../scripts/test-chromium-history-open.mjs", import.meta.url), "utf8"),
    readFile(new URL("../../../.github/workflows/chromium-webextension.yml", import.meta.url), "utf8"),
    readFile(new URL("../manifest.json", import.meta.url), "utf8").then(JSON.parse),
    readFile(new URL("../src/background.js", import.meta.url), "utf8")
  ]);
  for (const required of [
    "chromium.launchPersistentContext", "createNativePdfDownloadFixture",
    'page.waitForEvent("download"', "page.locator(item.selector).click()",
    "download.failure()", "readFile(await download.path())",
    "await page.close()", '"chrome://downloads/"',
    'history.locator("downloads-item")', 'row.locator("#fileLink")',
    "await fileLink.click(", "openFileRequiringGesture",
    "__pdfMagicHistoryOpenIds",
    "fixture.snapshot().requests[item.path]", "await context?.close()",
    "await rm(profile"
  ]) assert.ok(smoke.includes(required), required);
  assert.match(workflow, /node scripts\/test-chromium-history-open\.mjs "\$CHROMIUM_BINARY_PATH"/);
  assert.match(workflow, /playwright-core@1\.56\.1/);
  for (const forbidden of [
    "downloads.open(", "permissions.request(", "connectNative(",
    "sendNativeMessage(", "clamscan(", "shell: true"
  ]) assert.equal(smoke.includes(forbidden), false, forbidden);
  assert.deepEqual(manifest.permissions, []);
  assert.deepEqual(manifest.host_permissions, []);
  assert.deepEqual(manifest.optional_permissions, ["downloads"]);
  assert.ok(worker.trimEnd().endsWith("void 0;"));
});
