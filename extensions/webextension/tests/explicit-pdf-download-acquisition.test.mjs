import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";
import { createExplicitPdfDownloadAcquisition } from "../src/explicit-pdf-download-acquisition.js";

const request = (patch = {}) => ({
  version: 1, requestId: "attempt_1", source: "pdf-link",
  tabId: 4, frameId: 0, selectionId: "selected_1",
  userInitiated: true, ...patch
});
function fixture() {
  const listeners = new Set();
  const calls = [];
  const state = { selected: "selected_1", grant: true, ready: true,
    needed: true, safe: true, native: true };
  const permissionsApi = {
    contains: async (query) => {
      calls.push(["contains", query]);
      return state.grant;
    },
    onRemoved: {
      addListener(handler) { listeners.add(handler); },
      removeListener(handler) { listeners.delete(handler); }
    }
  };
  const downloadsApi = {
    download: async (options) => { calls.push(["download", options]); return 37; },
    cancel: async (id) => { calls.push(["cancel", id]); }
  };
  const coordinator = {
    get sourceAcquisitionReady() { return state.ready; },
    get sourceAcquisitionNeeded() { return state.needed; },
    get browserDownloadSafetyReady() { return state.safe; },
    get nativeScannerReady() { return state.native; },
    readCurrentSelectionId() { return state.selected; },
    resolveVerifiedPdfSource: async (context) => {
      calls.push(["resolve", context]);
      return { selectionId: context.selectionId,
        verified: true, url: "https://example.test/report.pdf?token=private" };
    }
  };
  // The adapter intentionally rejects accessor-based readiness properties,
  // so use stable own data fields and mutate those when testing invalidation.
  for (const [key, stateKey] of [
    ["sourceAcquisitionReady", "ready"],
    ["sourceAcquisitionNeeded", "needed"],
    ["browserDownloadSafetyReady", "safe"],
    ["nativeScannerReady", "native"]
  ]) Object.defineProperty(coordinator, key, {
    value: state[stateKey], writable: true, configurable: true
  });
  return {
    permissionsApi, downloadsApi, coordinator, state, calls,
    revoke: () => { for (const listener of listeners) {
      listener({ permissions: ["downloads"], origins: [] });
    } },
    listenerCount: () => listeners.size,
    action: () => createExplicitPdfDownloadAcquisition({
      downloadsApi, permissionsApi, coordinator
    })
  };
}

test("uses browser downloads.download with a verified source and non-overwriting save dialog", async () => {
  const f = fixture();
  const result = await f.action().acquire(request());
  assert.deepEqual(result, {
    status: "download-started", downloadId: 37, downloadStarted: true,
    scanVerified: false, authorizesScan: false, authorizesOpen: false
  });
  assert.ok(Object.isFrozen(result));
  assert.deepEqual(f.calls, [
    ["resolve", { selectionId: "selected_1", tabId: 4, frameId: 0 }],
    ["contains", { permissions: ["downloads"] }],
    ["download", {
      url: "https://example.test/report.pdf?token=private",
      saveAs: true, conflictAction: "uniquify"
    }]
  ]);
  assert.equal(f.listenerCount(), 0);
  assert.equal(JSON.stringify(result).includes("private"), false);
});

test("requires explicit validated user intent, not page URLs or proposed scan verdicts", async () => {
  for (const patch of [
    { userInitiated: false }, { requestId: "" }, { source: "download" },
    { frameId: -1 }, { selectionId: "/private/report.pdf" },
    { url: "https://example.test/report.pdf" }, { scanVerified: true }
  ]) {
    const f = fixture();
    assert.equal((await f.action().acquire(request(patch))).status, "unavailable");
    assert.equal(f.calls.length, 0);
  }
});

test("never downloads without all separately verified coordination prerequisites", async () => {
  for (const field of [
    "sourceAcquisitionReady", "sourceAcquisitionNeeded",
    "browserDownloadSafetyReady", "nativeScannerReady"
  ]) {
    const f = fixture();
    f.coordinator[field] = false;
    assert.equal((await f.action().acquire(request())).status, "unavailable");
    assert.equal(f.calls.length, 0);
  }
  const f = fixture();
  f.state.selected = "different_selection";
  assert.equal((await f.action().acquire(request())).status, "unavailable");
  assert.equal(f.calls.length, 0);
});

test("denied or missing downloads permission and required APIs fail closed", async () => {
  const f = fixture();
  f.state.grant = false;
  assert.equal((await f.action().acquire(request())).status, "unavailable");
  assert.equal(f.calls.filter(([kind]) => kind === "download").length, 0);
  const missing = createExplicitPdfDownloadAcquisition({
    coordinator: f.coordinator, downloadsApi: { download() { throw Error("must not run"); } },
    permissionsApi: f.permissionsApi
  });
  assert.equal((await missing.acquire(request({ requestId: "attempt_2" }))).status,
    "unavailable");
});

test("refuses unsafe, ambiguous, credentialed and unsupported browser source URLs", async () => {
  const invalid = [
    "file:///private/report.pdf", "blob:https://example.test/file.pdf",
    "data:application/pdf,bytes", "javascript:alert(1)",
    "https://user:secret@example.test/report.pdf",
    "https://example.test/report%2F.pdf",
    "https://example.test/report%5C.pdf",
    "https://example.test/report%00.pdf",
    "https://example.test/report%ZZ.pdf",
    "https://example.test/report.pdf\n",
    "https://example.test/" + "a".repeat(8193)
  ];
  for (const url of invalid) {
    const f = fixture();
    f.coordinator.resolveVerifiedPdfSource = async ({ selectionId }) => ({
      selectionId, verified: true, url
    });
    assert.equal((await f.action().acquire(request())).status, "unavailable", url.slice(0, 60));
    assert.equal(f.calls.some(([kind]) => kind === "download"), false);
  }
  const f = fixture();
  f.coordinator.resolveVerifiedPdfSource = async () => ({
    selectionId: "selected_1", verified: true, url: "https://example.test/file.pdf",
    maliciousOverride: true
  });
  assert.equal((await f.action().acquire(request())).status, "unavailable");
});

test("rechecks the selection after asynchronous verification and permission checks", async () => {
  const f = fixture();
  f.coordinator.resolveVerifiedPdfSource = async ({ selectionId }) => {
    f.state.selected = "other";
    return { selectionId, verified: true, url: "https://example.test/report.pdf" };
  };
  assert.equal((await f.action().acquire(request())).status, "unavailable");
  assert.equal(f.calls.some(([kind]) => kind === "download"), false);
  const next = fixture();
  next.permissionsApi.contains = async () => {
    next.state.selected = "other";
    return true;
  };
  assert.equal((await next.action().acquire(request())).status, "unavailable");
  assert.equal(next.calls.some(([kind]) => kind === "download"), false);
});

test("revocation while a download is pending requests cancellation without granting scan", async () => {
  const f = fixture();
  let finish;
  f.downloadsApi.download = () => new Promise(resolve => { finish = resolve; });
  const pending = f.action().acquire(request());
  await new Promise(resolve => setImmediate(resolve));
  assert.equal(typeof finish, "function");
  f.revoke();
  finish(37);
  assert.equal((await pending).status, "unavailable");
  assert.deepEqual(f.calls.filter(([kind]) => kind === "cancel"), [["cancel", 37]]);
  assert.equal(f.listenerCount(), 0);
});

test("stale selections after browser acceptance trigger best-effort cancellation", async () => {
  const f = fixture();
  f.downloadsApi.download = async () => {
    f.state.selected = "different";
    return 5;
  };
  assert.equal((await f.action().acquire(request())).status, "unavailable");
  assert.deepEqual(f.calls.filter(([kind]) => kind === "cancel"), [["cancel", 5]]);
});

test("reserves each request once across concurrent calls and failures", async () => {
  const f = fixture();
  const action = f.action();
  const [first, second] = await Promise.all([
    action.acquire(request()), action.acquire(request())
  ]);
  assert.equal(first.status, "download-started");
  assert.equal(second.status, "unavailable");
  assert.equal((await action.acquire(request())).status, "unavailable");
  assert.equal(f.calls.filter(([kind]) => kind === "download").length, 1);
});

test("bad browser acknowledgements and hostile coordinator objects fail closed", async () => {
  for (const reply of [null, undefined, true, "1", -1, 1.2, NaN]) {
    const f = fixture();
    f.downloadsApi.download = async () => reply;
    assert.equal((await f.action().acquire(request())).status, "unavailable");
  }
  const f = fixture();
  Object.defineProperty(f.coordinator, "nativeScannerReady", {
    get() { throw Error("secret"); }
  });
  assert.equal((await f.action().acquire(request())).status, "unavailable");
});

test("the acquisition mechanism is dormant and cannot open or bypass the native scanner", async () => {
  const read = path => readFile(new URL(path, import.meta.url), "utf8");
  const [source, manifestText, background, ci] = await Promise.all([
    read("../src/explicit-pdf-download-acquisition.js"),
    read("../manifest.json"), read("../src/background.js"),
    read("../../../.github/workflows/ci.yml")
  ]);
  const manifest = JSON.parse(manifestText);
  assert.deepEqual(manifest.permissions, []);
  assert.deepEqual(manifest.host_permissions, []);
  assert.deepEqual(manifest.optional_permissions, ["downloads"]);
  assert.ok(background.trimEnd().endsWith("void 0;"));
  assert.match(source, /downloads\.download\(\)/);
  assert.match(source, /saveAs: true, conflictAction: "uniquify"/);
  assert.match(ci, /node --test tests\/explicit-pdf-download-acquisition\.test\.mjs/);
  for (const forbidden of [
    "globalThis.", "chrome.", "browser.", "fetch(", "XMLHttpRequest",
    "downloads.open(", "openFile(", "sendNativeMessage(", "connectNative(",
    "permissions.request(", "window.open(", "scan-and-open", "clamscan("
  ]) assert.equal(source.includes(forbidden), false, forbidden);
});
