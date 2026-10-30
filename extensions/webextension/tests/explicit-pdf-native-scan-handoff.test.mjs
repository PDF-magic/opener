import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";
import { createExplicitPdfNativeScanHandoff } from "../src/explicit-pdf-native-scan-handoff.js";
import { createCompletedDownloadScanRequestGate } from "../src/download-scan-once.js";

const request = () => ({
  version: 1, requestId: "attempt_10", source: "pdf-link", tabId: 12,
  frameId: 3, selectionId: "selection_4", userInitiated: true
});
const acquisition = (id = 7) => ({
  status: "download-started", downloadId: id, downloadStarted: true,
  scanVerified: false, authorizesScan: false, authorizesOpen: false
});
const completion = (id = 7) => ({ kind: "completed", id });
const proof = (id = 7) => ({
  requestId: "attempt_10", source: "pdf-link", tabId: 12,
  frameId: 3, selectionId: "selection_4", downloadId: id, verified: true
});
const unavailable = {
  status: "unavailable", scanSubmitted: false,
  scanVerified: false, authorizesOpen: false
};
const success = {
  status: "submitted", scanSubmitted: true,
  scanVerified: false, authorizesOpen: false
};
const flush = () => new Promise(resolve => setImmediate(resolve));
function event() {
  const handlers = new Set();
  return {
    addListener(fn) { handlers.add(fn); },
    removeListener(fn) { handlers.delete(fn); },
    emit(change) { for (const fn of [...handlers]) fn(change); },
    get size() { return handlers.size; }
  };
}
function fixture() {
  const calls = [], searches = [], grants = [], receipts = [];
  const downloads = {
    onCreated: event(), onChanged: event(), onErased: event(),
    search(query) {
      searches.push(query);
      return Promise.resolve([{
        id: query.id, state: "complete", exists: true,
        paused: false, canResume: false, bytesReceived: 1024,
        totalBytes: 1024, filename: "/tmp/document.pdf",
        mime: "application/pdf", danger: "safe"
      }]);
    }
  };
  const permissions = {
    onRemoved: event(),
    contains(query) { grants.push(query); return Promise.resolve(true); }
  };
  const coordinator = {
    explicitPdfScanReady: true, nativeScannerReady: true,
    readVerifiedAcquiredPdf(reference) {
      receipts.push(reference);
      return proof();
    },
    submitCompletedPdfDownload(candidate) {
      calls.push(candidate);
      return Promise.resolve({ accepted: true });
    }
  };
  const gate = createCompletedDownloadScanRequestGate(downloads);
  const handoff = createExplicitPdfNativeScanHandoff({
    downloadsApi: downloads, permissionsApi: permissions,
    coordinator, scanGate: gate
  });
  return { downloads, permissions, coordinator, gate, handoff, calls, searches, grants, receipts };
}
function cleanup(f) {
  f.handoff.dispose();
  f.gate.dispose();
  assert.equal(f.downloads.onCreated.size, 0);
  assert.equal(f.downloads.onChanged.size, 0);
  assert.equal(f.downloads.onErased.size, 0);
  assert.equal(f.permissions.onRemoved.size, 0);
}
function submit(f, details = {}) {
  return f.handoff.submitAcquiredPdf({
    request: request(), acquisition: acquisition(),
    completion: completion(), ...details
  });
}

test("explicit acquisition submits a completed PDF to the reviewed native scan adapter", async () => {
  const f = fixture();
  assert.deepEqual(await submit(f), success);
  assert.equal(f.calls.length, 1);
  assert.deepEqual(f.calls[0], { id: 7, localPath: "/tmp/document.pdf" });
  assert.ok(Object.isFrozen(f.calls[0]));
  assert.deepEqual(f.receipts[0], {
    requestId: "attempt_10", source: "pdf-link", tabId: 12,
    frameId: 3, selectionId: "selection_4", downloadId: 7
  });
  assert.ok(Object.isFrozen(f.receipts[0]));
  assert.deepEqual(f.searches, Array.from({ length: 6 }, () => ({ id: 7 })));
  assert.deepEqual(f.grants, Array.from({ length: 6 }, () => ({
    permissions: ["downloads"]
  })));
  assert.deepEqual(await submit(f), unavailable);
  assert.equal(f.calls.length, 1);
  cleanup(f);
});

test("untrusted acquisition metadata and mismatched completion fail before browser access", async () => {
  for (const difference of [
    { acquisition: null }, { acquisition: { ...acquisition(), status: "error" } },
    { acquisition: { ...acquisition(), authorizesOpen: true } },
    { acquisition: { ...acquisition(), transferComplete: true } },
    { acquisition: { ...acquisition(), downloadStarted: "true" } },
    { acquisition: acquisition(-1) },
    { completion: completion(8) },
    { completion: { ...completion(), filename: "secret.pdf" } },
    { request: { ...request(), userInitiated: false } },
    { request: { ...request(), selectionId: "attempt_10" } }
  ]) {
    const f = fixture();
    assert.deepEqual(await submit(f, difference), unavailable);
    assert.deepEqual(f.searches, []);
    assert.deepEqual(f.calls, []);
    cleanup(f);
  }
});

test("missing trusted native capabilities never submit anything", async () => {
  for (const changed of [
    { nativeScannerReady: false }, { explicitPdfScanReady: false },
    { nativeScannerReady: "true" }, { readVerifiedAcquiredPdf: null },
    { submitCompletedPdfDownload: null }
  ]) {
    const f = fixture();
    Object.assign(f.coordinator, changed);
    assert.deepEqual(await submit(f), unavailable);
    assert.equal(f.searches.length, 0);
    cleanup(f);
  }
  const f = fixture();
  f.gate.dispose();
  f.handoff.dispose();
  const empty = createExplicitPdfNativeScanHandoff({
    downloadsApi: f.downloads, permissionsApi: f.permissions,
    coordinator: f.coordinator
  });
  assert.deepEqual(await empty.submitAcquiredPdf({
    request: request(), acquisition: acquisition(), completion: completion()
  }), unavailable);
  assert.equal(f.searches.length, 0);
  empty.dispose();
});

test("mismatched trusted request, selected PDF and browser download ID fail closed", async () => {
  for (const change of [
    { requestId: "other" }, { selectionId: "other" }, { downloadId: 8 },
    { source: "toolbar" }, { tabId: 13 }, { frameId: 0 },
    { verified: false }, { verified: "true" }, { path: "/secret.pdf" }
  ]) {
    const f = fixture();
    f.coordinator.readVerifiedAcquiredPdf = () => ({ ...proof(), ...change });
    assert.deepEqual(await submit(f), unavailable);
    assert.equal(f.calls.length, 0);
    assert.equal(f.searches.length, 0);
    cleanup(f);
  }
});

test("accessor, inherited and throwing proof cannot forge a scan", async () => {
  for (const bad of [
    Object.create(proof()),
    new Proxy({}, { ownKeys() { throw Error("/private/path"); } }),
    { ...proof(), get verified() { throw Error("/private/path"); } },
    Promise.resolve(proof()), null
  ]) {
    const f = fixture();
    f.coordinator.readVerifiedAcquiredPdf = () => bad;
    assert.deepEqual(await submit(f), unavailable);
    assert.equal(f.calls.length, 0);
    cleanup(f);
  }
  const f = fixture();
  f.coordinator.submitCompletedPdfDownload = async () => {
    throw Error("/private/path/secret.pdf");
  };
  const response = await submit(f);
  assert.deepEqual(response, unavailable);
  assert.doesNotMatch(JSON.stringify(response), /private|secret/);
  cleanup(f);
});

test("incomplete downloads, browser danger warnings and non-PDF MIME block submission", async () => {
  for (const change of [
    { state: "in_progress" }, { exists: false },
    { bytesReceived: 2 }, { filename: "/tmp/document.pdf.crdownload" },
    { danger: "file" }, { danger: "accepted" }, { mime: "text/html" }
  ]) {
    const f = fixture();
    const search = f.downloads.search;
    f.downloads.search = query =>
      search(query).then(rows => rows.map(x => ({ ...x, ...change })));
    assert.deepEqual(await submit(f), unavailable, JSON.stringify(change));
    assert.equal(f.calls.length, 0);
    cleanup(f);
  }
});

test("missing and revoked downloads permissions block native submission", async () => {
  const f = fixture();
  f.permissions.contains = () => Promise.resolve(false);
  assert.deepEqual(await submit(f), unavailable);
  assert.equal(f.calls.length, 0);
  cleanup(f);

  const g = fixture();
  let release;
  g.downloads.search = () => new Promise(resolve => { release = resolve; });
  const pending = submit(g);
  await flush();
  g.permissions.onRemoved.emit({ permissions: ["downloads"], origins: [] });
  release([{
    id: 7, state: "complete", exists: true, paused: false, canResume: false,
    bytesReceived: 1024, totalBytes: 1024, filename: "/tmp/document.pdf",
    mime: "application/pdf", danger: "safe"
  }]);
  assert.deepEqual(await pending, unavailable);
  assert.equal(g.calls.length, 0);
  cleanup(g);
});

test("selection changes during browser metadata lookup block native submission", async () => {
  const f = fixture();
  const search = f.downloads.search;
  let calls = 0;
  f.downloads.search = query => {
    calls++;
    if (calls === 3) {
      f.coordinator.readVerifiedAcquiredPdf = () =>
        ({ ...proof(), selectionId: "new-selection" });
    }
    return search(query);
  };
  assert.deepEqual(await submit(f), unavailable);
  assert.equal(f.calls.length, 0);
  cleanup(f);
});

test("replaced callbacks invalidate the original verified association", async () => {
  const f = fixture();
  const search = f.downloads.search;
  f.downloads.search = query => {
    f.coordinator.readVerifiedAcquiredPdf = () => proof();
    return search(query);
  };
  assert.deepEqual(await submit(f), unavailable);
  assert.equal(f.calls.length, 0);
  cleanup(f);
});

test("native rejection or dubious acknowledgements never imply verified scanning", async () => {
  for (const answer of [
    { accepted: false }, { accepted: "true" },
    { scanVerified: true, authorizesOpen: true }, null
  ]) {
    const f = fixture();
    f.coordinator.submitCompletedPdfDownload = async () => answer;
    assert.deepEqual(await submit(f), unavailable);
    cleanup(f);
  }
});

test("the session gate blocks two explicit request IDs for the same download", async () => {
  const f = fixture();
  assert.deepEqual(await submit(f), success);
  const again = { ...request(), requestId: "new-attempt" };
  const former = f.coordinator.readVerifiedAcquiredPdf;
  f.coordinator.readVerifiedAcquiredPdf = ref =>
    ({ ...former(ref), requestId: ref.requestId });
  assert.deepEqual(await submit(f, { request: again }), unavailable);
  assert.equal(f.calls.length, 1);
  cleanup(f);
});

test("dispose blocks future submissions and invalidates a pending native acknowledgement", async () => {
  const f = fixture();
  let done;
  f.coordinator.submitCompletedPdfDownload = () =>
    new Promise(resolve => { done = resolve; });
  const pending = submit(f);
  for (let i = 0; i < 10 && !done; i++) await flush();
  assert.equal(typeof done, "function");
  f.handoff.dispose();
  done({ accepted: true });
  assert.deepEqual(await pending, unavailable);
  assert.deepEqual(await submit(f), unavailable);
  cleanup(f);
});

test("successful public result cannot expose local paths or claim opening authorization", async () => {
  const f = fixture();
  const out = await submit(f);
  assert.deepEqual(out, success);
  assert.ok(Object.isFrozen(out));
  assert.equal(JSON.stringify(out).includes("/tmp/document.pdf"), false);
  assert.equal(out.scanVerified, false);
  assert.equal(out.authorizesOpen, false);
  cleanup(f);
});

test("shipped WebExtension remains inactive without native privileges or opening side effects", async () => {
  const code = await readFile(new URL("../src/explicit-pdf-native-scan-handoff.js", import.meta.url), "utf8");
  const background = await readFile(new URL("../src/background.js", import.meta.url), "utf8");
  const manifest = JSON.parse(await readFile(new URL("../manifest.json", import.meta.url), "utf8"));
  assert.match(background, /void 0;/);
  assert.deepEqual(manifest.permissions, []);
  assert.deepEqual(manifest.host_permissions, []);
  for (const forbidden of [
    "sendNativeMessage(", "connectNative(", "window.open(",
    "downloads.open(", "acceptDanger(", "fetch(", "node:fs",
    "localStorage", "permissions.request("
  ]) assert.equal(code.includes(forbidden), false, forbidden);
});
